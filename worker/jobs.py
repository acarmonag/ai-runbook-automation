"""
ARQ job definitions — runs inside the agent-worker container.

Each job is an async function. ARQ passes ctx (worker context) as first arg.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import os
from typing import Any

from arq.connections import ArqRedis

from db.database import AsyncSessionLocal
from db.incident_store import create_incident, update_incident, get_incident
from agent.actions.registry import build_default_registry
from agent.agent import SREAgent
from agent.approval_gate import ApprovalGate, ApprovalMode
from agent.runbook_registry import RunbookRegistry
from worker.publisher import publish_incident_update
from worker.pir import generate_pir

logger = logging.getLogger(__name__)


async def process_alert(ctx: dict[str, Any], incident_id: str, alert: dict[str, Any]) -> dict[str, Any]:
    """
    Main agent job: run the full OBSERVE→REASON→ACT→VERIFY→REPORT loop
    for one alert, writing state to PostgreSQL and publishing changes
    to Redis pub/sub as the incident progresses.
    """
    session_factory = AsyncSessionLocal

    try:
        from agent.metrics import active_incidents
        active_incidents.inc()
    except Exception:
        pass

    async with session_factory() as session:
        # Row may already exist (created by API on enqueue) — upsert to PROCESSING.
        existing = await get_incident(session, incident_id)
        if existing:
            await update_incident(session, incident_id, {"status": "PROCESSING"})
        else:
            await create_incident(session, {
                "incident_id": incident_id,
                "alert_name": alert.get("labels", {}).get("alertname", "Unknown"),
                "alert": alert,
                "status": "PROCESSING",
            })
        await publish_incident_update(ctx["redis"], incident_id, "PROCESSING")

    # Build agent — read mode from Redis so UI toggle takes effect immediately
    registry = build_default_registry()
    runbook_registry = RunbookRegistry()
    approval_gate = ApprovalGate(
        mode=await _resolve_approval_mode(ctx["redis"]),
        redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379"),
    )
    agent = SREAgent(
        action_registry=registry,
        runbook_registry=runbook_registry,
        approval_gate=approval_gate,
    )

    try:
        # Run the synchronous agent loop in a thread pool so the async event
        # loop stays responsive while the approval gate is blocking on human input.
        loop = asyncio.get_event_loop()
        report = await loop.run_in_executor(
            None,
            functools.partial(agent.run, alert, incident_id=incident_id),
        )
    except Exception as exc:
        logger.exception(f"[{incident_id}] Agent crashed: {exc}")
        async with session_factory() as session:
            await update_incident(session, incident_id, {"status": "FAILED"})
        await publish_incident_update(ctx["redis"], incident_id, "FAILED")
        raise

    # Persist final report
    final_status = report.get("status", "FAILED")
    async with session_factory() as session:
        await update_incident(session, incident_id, {
            "status": final_status,
            "summary": report.get("summary"),
            "root_cause": report.get("root_cause"),
            "actions_taken": report.get("actions_taken", []),
            "recommendations": report.get("recommendations", []),
            "reasoning_transcript": report.get("reasoning_transcript", []),
            "state_history": report.get("state_history", []),
            "full_agent_response": report.get("full_agent_response"),
            "resolved_at": _now_dt() if final_status in ("RESOLVED", "ESCALATED") else None,
        })

    await publish_incident_update(ctx["redis"], incident_id, final_status)

    # Record Prometheus metrics
    try:
        from datetime import datetime, timezone
        from agent.metrics import record_incident, active_incidents
        started_str = report.get("started_at") or _iso_now()
        resolved_str = report.get("resolved_at") or _iso_now()
        started_dt = datetime.fromisoformat(started_str.rstrip("Z"))
        resolved_dt = datetime.fromisoformat(resolved_str.rstrip("Z"))
        duration = (resolved_dt - started_dt).total_seconds()
        record_incident(
            status=final_status,
            alert_name=alert.get("labels", {}).get("alertname", "Unknown"),
            duration_seconds=max(duration, 0),
            actions=report.get("actions_taken", []),
            tokens_used=report.get("llm_tokens_used", 0),
            model=report.get("llm_model", "unknown"),
        )
        active_incidents.dec()
    except Exception as exc:
        logger.warning(f"[{incident_id}] Failed to record metrics: {exc}")

    # Auto-generate PIR for all terminal incidents
    if final_status in ("RESOLVED", "ESCALATED", "FAILED"):
        await generate_pir(incident_id, report)

    # Cleanup: delete correlation key so the next identical alert fires a fresh incident.
    # Without this, the 300s TTL window prevents re-testing the same scenario.
    await _delete_correlation_key(alert, ctx["redis"])

    # Reset mock Prometheus scenario state back to INCIDENT for the next test run.
    await _reset_mock_prometheus()

    logger.info(f"[{incident_id}] Job complete: {final_status}")
    return {"incident_id": incident_id, "status": final_status}


async def _delete_correlation_key(alert: dict[str, Any], redis_client: Any) -> None:
    """Remove the correlation dedup key so an identical alert triggers a new incident."""
    try:
        labels = alert.get("labels", {})
        service = (labels.get("service") or labels.get("job") or "unknown").lower()
        alertname = labels.get("alertname", "unknown").lower()
        key = f"corr:{service}:{alertname}"
        await redis_client.delete(key)
        logger.debug(f"Deleted correlation key: {key}")
    except Exception as exc:
        logger.warning(f"Could not delete correlation key: {exc}")


async def _reset_mock_prometheus() -> None:
    """POST to mock Prometheus to reset scenario state to INCIDENT for the next run."""
    import httpx
    prometheus_url = os.environ.get("PROMETHEUS_URL", "http://mock-prometheus:9091")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(f"{prometheus_url}/api/v1/reset")
        logger.debug("Mock Prometheus scenario state reset to INCIDENT")
    except Exception as exc:
        logger.debug(f"Could not reset mock Prometheus: {exc}")


def _iso_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _now_dt():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


async def _resolve_approval_mode(redis_client: Any) -> ApprovalMode:
    """Read mode from Redis (set by UI toggle); fall back to APPROVAL_MODE env var."""
    try:
        raw = await redis_client.get("agent:mode")
        if raw:
            mode_str = raw.decode() if isinstance(raw, bytes) else str(raw)
            return ApprovalMode(mode_str.upper())
    except Exception:
        pass
    env_raw = os.environ.get("APPROVAL_MODE", "AUTO").upper()
    try:
        return ApprovalMode(env_raw)
    except ValueError:
        return ApprovalMode.AUTO
