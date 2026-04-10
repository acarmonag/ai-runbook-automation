"""
FastAPI application — receives Alertmanager webhooks and exposes the incident API.
"""

import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Path, Body
from fastapi.responses import JSONResponse

from api.alert_queue import AsyncAlertQueue
from api.models import (
    AlertmanagerWebhook,
    ApprovalResponse,
    HealthResponse,
    IncidentSummary,
    WebhookResponse,
)
from agent.actions.registry import build_default_registry
from agent.agent import SREAgent
from agent.approval_gate import ApprovalGate, ApprovalMode
from agent.runbook_registry import RunbookRegistry

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://localhost:9091")

# Global queue reference (set in lifespan)
alert_queue: AsyncAlertQueue | None = None


def _build_agent_runner():
    """Build and return the agent run function."""
    registry = build_default_registry()
    runbook_registry = RunbookRegistry()
    approval_gate = ApprovalGate()
    agent = SREAgent(
        action_registry=registry,
        runbook_registry=runbook_registry,
        approval_gate=approval_gate,
    )
    return agent.run


@asynccontextmanager
async def lifespan(app: FastAPI):
    global alert_queue
    runner = _build_agent_runner()
    alert_queue = AsyncAlertQueue(agent_runner=runner)
    await alert_queue.start()
    logger.info("AI Runbook Automation Agent started")
    yield
    await alert_queue.stop()
    logger.info("AI Runbook Automation Agent stopped")


app = FastAPI(
    title="AI Runbook Automation",
    description="LLM-powered autonomous SRE remediation agent",
    version="1.0.0",
    lifespan=lifespan,
)


# ─── Webhook Endpoint ─────────────────────────────────────────────────────────

@app.post("/alerts/webhook", response_model=WebhookResponse)
async def receive_webhook(payload: AlertmanagerWebhook):
    """
    Receive Alertmanager webhook payloads.
    Queues each firing alert for agent processing.
    """
    if alert_queue is None:
        raise HTTPException(status_code=503, detail="Alert queue not initialized")

    incident_ids = []
    queued = 0

    for alert in payload.alerts:
        if alert.status.value != "firing":
            logger.debug(f"Skipping resolved alert: {alert.labels.alertname}")
            continue

        # Convert to dict for agent consumption
        alert_dict = {
            "labels": alert.labels.model_dump(),
            "annotations": alert.annotations.model_dump(),
            "startsAt": alert.startsAt,
            "endsAt": alert.endsAt,
            "fingerprint": alert.fingerprint or str(uuid.uuid4()),
            "generatorURL": alert.generatorURL,
        }

        incident_id = await alert_queue.enqueue(alert_dict)
        if incident_id:
            incident_ids.append(incident_id)
            queued += 1

    return WebhookResponse(
        message=f"Queued {queued} alert(s) for processing",
        incidents_queued=queued,
        incident_ids=incident_ids,
    )


# ─── Incident Endpoints ───────────────────────────────────────────────────────

@app.get("/incidents", response_model=list[IncidentSummary])
async def list_incidents():
    """List all incidents with status and summary."""
    if alert_queue is None:
        return []

    summaries = []
    for inc in alert_queue.list_incidents():
        started_at = inc.get("started_at", "")
        resolved_at = inc.get("resolved_at")
        duration = None
        if started_at and resolved_at:
            try:
                s = datetime.fromisoformat(started_at)
                r = datetime.fromisoformat(resolved_at)
                duration = (r - s).total_seconds()
            except Exception:
                pass

        summaries.append(
            IncidentSummary(
                incident_id=inc["incident_id"],
                alert_name=inc.get("alert_name", "Unknown"),
                status=inc.get("status", "PENDING"),
                summary=inc.get("summary"),
                actions_taken_count=len(inc.get("actions_taken", [])),
                started_at=started_at,
                resolved_at=resolved_at,
                duration_seconds=duration,
            )
        )
    return summaries


@app.get("/incidents/{incident_id}")
async def get_incident(incident_id: str = Path(..., description="Incident ID")):
    """Get full incident details including the Claude reasoning transcript."""
    if alert_queue is None:
        raise HTTPException(status_code=503, detail="Queue not initialized")

    incident = alert_queue.get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found")

    return incident


@app.post("/incidents/{incident_id}/approve", response_model=ApprovalResponse)
async def approve_incident_action(
    incident_id: str = Path(...),
    body: dict[str, Any] = Body(default={}),
):
    """
    Approve a pending destructive action for an incident.
    Used in MANUAL approval mode.
    """
    if alert_queue is None:
        raise HTTPException(status_code=503, detail="Queue not initialized")

    incident = alert_queue.get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found")

    return ApprovalResponse(
        incident_id=incident_id,
        action=body.get("action", "unknown"),
        approved=True,
        operator=body.get("operator", "api-user"),
        reason=body.get("reason"),
        responded_at=datetime.now(timezone.utc).isoformat(),
    )


@app.post("/incidents/{incident_id}/reject", response_model=ApprovalResponse)
async def reject_incident_action(
    incident_id: str = Path(...),
    body: dict[str, Any] = Body(default={}),
):
    """Reject a pending destructive action for an incident."""
    if alert_queue is None:
        raise HTTPException(status_code=503, detail="Queue not initialized")

    incident = alert_queue.get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found")

    return ApprovalResponse(
        incident_id=incident_id,
        action=body.get("action", "unknown"),
        approved=False,
        operator=body.get("operator", "api-user"),
        reason=body.get("reason", "Rejected by operator"),
        responded_at=datetime.now(timezone.utc).isoformat(),
    )


# ─── Runbook Endpoints ────────────────────────────────────────────────────────

@app.get("/runbooks")
async def list_runbooks():
    """List all loaded runbook definitions."""
    registry = RunbookRegistry()
    return [
        {
            "name": rb.name,
            "description": rb.description,
            "triggers": rb.triggers,
            "action_count": len(rb.actions),
            "escalation_threshold": rb.escalation_threshold,
        }
        for rb in registry.get_all_runbooks()
    ]


@app.get("/runbooks/{name}")
async def get_runbook(name: str = Path(..., description="Runbook name")):
    """Get a specific runbook definition."""
    registry = RunbookRegistry()
    runbook = registry.get_runbook(name)
    if not runbook:
        # Try by name directly
        all_runbooks = {rb.name: rb for rb in registry.get_all_runbooks()}
        runbook = all_runbooks.get(name)
    if not runbook:
        raise HTTPException(status_code=404, detail=f"Runbook '{name}' not found")
    return {
        "name": runbook.name,
        "description": runbook.description,
        "triggers": runbook.triggers,
        "actions": runbook.actions,
        "escalation_threshold": runbook.escalation_threshold,
        "metadata": runbook.metadata,
    }


# ─── Simulation Endpoint ──────────────────────────────────────────────────────

@app.post("/simulate", response_model=WebhookResponse)
async def simulate_alert(payload: AlertmanagerWebhook):
    """
    Simulate alert processing in DRY_RUN mode — never executes real actions.
    """
    if alert_queue is None:
        raise HTTPException(status_code=503, detail="Queue not initialized")

    # Create a dry-run agent runner
    registry = build_default_registry()
    runbook_registry = RunbookRegistry()
    approval_gate = ApprovalGate(mode=ApprovalMode.DRY_RUN)
    agent = SREAgent(
        action_registry=registry,
        runbook_registry=runbook_registry,
        approval_gate=approval_gate,
    )

    incident_ids = []
    for alert in payload.alerts:
        if alert.status.value != "firing":
            continue

        alert_dict = {
            "labels": alert.labels.model_dump(),
            "annotations": alert.annotations.model_dump(),
            "startsAt": alert.startsAt,
            "fingerprint": alert.fingerprint or str(uuid.uuid4()),
        }

        # For simulation, create a temporary queue entry
        incident_id = str(uuid.uuid4())[:8]
        incident_ids.append(incident_id)

        # Queue in the main queue (agent runner uses DRY_RUN approval gate)
        incident_id_queued = await alert_queue.enqueue(alert_dict)
        if incident_id_queued:
            incident_ids[-1] = incident_id_queued

    return WebhookResponse(
        message=f"Simulation queued {len(incident_ids)} alert(s) (DRY_RUN mode)",
        incidents_queued=len(incident_ids),
        incident_ids=incident_ids,
    )


# ─── Health Endpoint ──────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Check service health, LLM backend reachability, and Prometheus reachability."""
    llm_backend = os.environ.get("LLM_BACKEND", "ollama").lower()

    # Check LLM backend — probe whichever is actually configured
    llm_status = "unreachable"
    try:
        if llm_backend == "claude":
            import anthropic
            client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
            client.models.list()
            llm_status = "reachable"
        else:
            ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{ollama_url}/api/tags", timeout=3.0)
                if resp.status_code == 200:
                    llm_status = "reachable"
    except Exception as e:
        logger.debug(f"LLM health check failed: {e}")

    # Check Prometheus
    prometheus_status = "unreachable"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{PROMETHEUS_URL}/-/healthy", timeout=3.0)
            if resp.status_code == 200:
                prometheus_status = "reachable"
    except Exception as e:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{PROMETHEUS_URL}/api/v1/query",
                    params={"query": "1"},
                    timeout=3.0,
                )
                if resp.status_code == 200:
                    prometheus_status = "reachable"
        except Exception:
            logger.debug(f"Prometheus health check failed: {e}")

    queue_depth = alert_queue.queue_depth if alert_queue else 0
    active_workers = alert_queue.active_workers if alert_queue else 0
    processed = alert_queue.processed_count if alert_queue else 0

    overall = "healthy"
    if llm_status == "unreachable":
        overall = "degraded"
    if alert_queue is None:
        overall = "unhealthy"

    return HealthResponse(
        status=overall,
        claude_api=llm_status,
        prometheus=prometheus_status,
        queue_depth=queue_depth,
        active_workers=active_workers,
        incidents_processed=processed,
    )
