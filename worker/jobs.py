"""
ARQ job definitions — runs inside the agent-worker container.

Each job is an async function. ARQ passes ctx (worker context) as first arg.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from arq.connections import ArqRedis

logger = logging.getLogger(__name__)


async def process_alert(ctx: dict[str, Any], incident_id: str, alert: dict[str, Any]) -> dict[str, Any]:
    """
    Main agent job: run the full OBSERVE→REASON→ACT→VERIFY→REPORT loop
    for one alert, writing state to PostgreSQL and publishing changes
    to Redis pub/sub as the incident progresses.
    """
    from db.database import AsyncSessionLocal
    from db.incident_store import create_incident, update_incident
    from agent.actions.registry import build_default_registry
    from agent.agent import SREAgent
    from agent.approval_gate import ApprovalGate
    from agent.runbook_registry import RunbookRegistry
    from worker.publisher import publish_incident_update

    session_factory = AsyncSessionLocal

    try:
        from agent.metrics import active_incidents
        active_incidents.inc()
    except Exception:
        pass

    async with session_factory() as session:
        # Persist the incident row (PENDING → PROCESSING)
        await create_incident(session, {
            "incident_id": incident_id,
            "alert_name": alert.get("labels", {}).get("alertname", "Unknown"),
            "alert": alert,
            "status": "PROCESSING",
        })
        await publish_incident_update(ctx["redis"], incident_id, "PROCESSING")

    # Build agent
    registry = build_default_registry()
    runbook_registry = RunbookRegistry()
    approval_gate = ApprovalGate()
    agent = SREAgent(
        action_registry=registry,
        runbook_registry=runbook_registry,
        approval_gate=approval_gate,
    )

    try:
        report = agent.run(alert)
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
            "resolved_at": _iso_now() if final_status in ("RESOLVED", "ESCALATED") else None,
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

    # Auto-generate PIR for resolved incidents
    if final_status == "RESOLVED":
        from worker.pir import generate_pir
        await generate_pir(incident_id, report)

    logger.info(f"[{incident_id}] Job complete: {final_status}")
    return {"incident_id": incident_id, "status": final_status}


def _iso_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
