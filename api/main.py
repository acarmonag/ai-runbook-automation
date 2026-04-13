from __future__ import annotations

"""
FastAPI application — alert intake, incident API, WebSocket hub, health.

Agent processing is delegated to agent-worker via Redis/ARQ.
This service only handles HTTP + WebSocket + persistence reads.
"""

import asyncio
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import Depends, FastAPI, HTTPException, Path, Body, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from api.alert_queue import AlertQueue
from api.auth import require_api_key
from api.models import (
    AlertmanagerWebhook,
    ApprovalResponse,
    HealthResponse,
    IncidentSummary,
    WebhookResponse,
)
from api.ws_manager import WebSocketManager
from db.database import create_tables, get_session
from db.incident_store import (
    create_incident,
    get_incident,
    get_mttr_stats,
    list_incidents,
    update_incident,
)
from agent.runbook_registry import RunbookRegistry

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://localhost:9091")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")

alert_queue = AlertQueue()
ws_manager = WebSocketManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create DB tables
    await create_tables()
    # Connect alert queue to Redis
    await alert_queue.start()
    # Start Redis pub/sub listener → broadcast to WebSocket clients
    listener_task = asyncio.create_task(_redis_listener())
    logger.info("AI Runbook Automation API started")
    yield
    listener_task.cancel()
    await alert_queue.stop()
    logger.info("AI Runbook Automation API stopped")


async def _redis_listener() -> None:
    """Subscribe to incident_updates channel and push to WebSocket clients."""
    import redis.asyncio as aioredis

    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    pubsub = r.pubsub()
    await pubsub.subscribe("incident_updates")
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                await ws_manager.broadcast(message["data"])
    except asyncio.CancelledError:
        pass
    finally:
        await pubsub.unsubscribe("incident_updates")
        await r.aclose()


app = FastAPI(
    title="AI Runbook Automation",
    description="LLM-powered autonomous SRE remediation agent",
    version="2.0.0",
    lifespan=lifespan,
    dependencies=[Depends(require_api_key)],
)

_cors_origins = [o.strip() for o in os.environ.get(
    "CORS_ORIGINS", "http://localhost:3000"
).split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── WebSocket ────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Real-time incident update stream."""
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep alive — client can send pings
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


# ─── Webhook Endpoint ─────────────────────────────────────────────────────────

@app.post("/alerts/webhook", response_model=WebhookResponse)
async def receive_webhook(
    payload: AlertmanagerWebhook,
    session: AsyncSession = Depends(get_session),
):
    incident_ids = []
    queued = 0

    for alert in payload.alerts:
        if alert.status.value != "firing":
            continue

        alert_dict = {
            "labels": alert.labels.model_dump(),
            "annotations": alert.annotations.model_dump(),
            "startsAt": alert.startsAt,
            "endsAt": alert.endsAt,
            "fingerprint": alert.fingerprint or str(uuid.uuid4()),
            "generatorURL": alert.generatorURL,
        }

        result = await alert_queue.enqueue(alert_dict)
        if result is None:
            continue

        incident_id, is_new = result
        incident_ids.append(incident_id)

        if is_new:
            # Pre-create the incident row so it's visible immediately.
            await create_incident(session, {
                "incident_id": incident_id,
                "alert_name": alert.labels.alertname,
                "alert": alert_dict,
                "status": "PENDING",
            })
            queued += 1
        # Correlated alerts are silently merged — no new row or job.

    return WebhookResponse(
        message=f"Queued {queued} alert(s) for processing",
        incidents_queued=queued,
        incident_ids=incident_ids,
    )


# ─── Incident Endpoints ───────────────────────────────────────────────────────

@app.get("/incidents", response_model=list[IncidentSummary])
async def list_incidents_endpoint(session: AsyncSession = Depends(get_session)):
    incidents = await list_incidents(session)
    result = []
    for inc in incidents:
        duration = None
        if inc.started_at and inc.resolved_at:
            duration = (inc.resolved_at - inc.started_at).total_seconds()
        result.append(IncidentSummary(
            incident_id=inc.incident_id,
            alert_name=inc.alert_name,
            status=inc.status,
            summary=inc.summary,
            actions_taken_count=len(inc.actions_taken or []),
            started_at=inc.started_at.isoformat(),
            resolved_at=inc.resolved_at.isoformat() if inc.resolved_at else None,
            duration_seconds=duration,
        ))
    return result


@app.get("/incidents/{incident_id}")
async def get_incident_endpoint(
    incident_id: str = Path(...),
    session: AsyncSession = Depends(get_session),
):
    inc = await get_incident(session, incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found")
    return inc.to_dict()


@app.get("/incidents/{incident_id}/pir")
async def get_pir(
    incident_id: str = Path(...),
    session: AsyncSession = Depends(get_session),
):
    """Return the auto-generated Post-Incident Review for a resolved incident."""
    inc = await get_incident(session, incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found")
    if not inc.pir:
        raise HTTPException(status_code=404, detail="PIR not yet generated")
    return inc.pir


@app.post("/incidents/{incident_id}/approve", response_model=ApprovalResponse)
async def approve_action(
    incident_id: str = Path(...),
    body: dict[str, Any] = Body(default={}),
    session: AsyncSession = Depends(get_session),
):
    inc = await get_incident(session, incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found")
    await update_incident(session, incident_id, {"approval_state": "APPROVED"})
    return ApprovalResponse(
        incident_id=incident_id,
        action=body.get("action", "unknown"),
        approved=True,
        operator=body.get("operator", "api-user"),
        reason=body.get("reason"),
        responded_at=datetime.now(timezone.utc).isoformat(),
    )


@app.post("/incidents/{incident_id}/reject", response_model=ApprovalResponse)
async def reject_action(
    incident_id: str = Path(...),
    body: dict[str, Any] = Body(default={}),
    session: AsyncSession = Depends(get_session),
):
    inc = await get_incident(session, incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found")
    await update_incident(session, incident_id, {"approval_state": "REJECTED"})
    return ApprovalResponse(
        incident_id=incident_id,
        action=body.get("action", "unknown"),
        approved=False,
        operator=body.get("operator", "api-user"),
        reason=body.get("reason", "Rejected by operator"),
        responded_at=datetime.now(timezone.utc).isoformat(),
    )


# ─── Stats Endpoint ───────────────────────────────────────────────────────────

@app.get("/stats")
async def get_stats(session: AsyncSession = Depends(get_session)):
    """MTTR and SLO stats for the dashboard."""
    return await get_mttr_stats(session)


@app.get("/correlations")
async def list_correlations():
    """Active alert correlation groups — useful for observability/debugging."""
    groups = await alert_queue._correlator.active_groups()
    return {"active_groups": groups, "count": len(groups)}


# ─── Prometheus Metrics ───────────────────────────────────────────────────────

@app.get("/metrics")
async def prometheus_metrics():
    """Expose Prometheus metrics for scraping."""
    from agent.metrics import metrics_output
    body, content_type = metrics_output()
    return Response(content=body, media_type=content_type)


# ─── Runbook Endpoints ────────────────────────────────────────────────────────

@app.get("/runbooks")
async def list_runbooks_endpoint():
    registry = RunbookRegistry()
    return [
        {
            "name": rb.name,
            "description": rb.description,
            "triggers": rb.triggers,
            "action_count": len(rb.actions),
            "actions": rb.actions,
            "escalation_threshold": rb.escalation_threshold,
            "metadata": rb.metadata,
        }
        for rb in registry.get_all_runbooks()
    ]


@app.get("/runbooks/{name}")
async def get_runbook_endpoint(name: str = Path(...)):
    registry = RunbookRegistry()
    runbook = registry.get_runbook(name) or next(
        (rb for rb in registry.get_all_runbooks() if rb.name == name), None
    )
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


@app.get("/runbooks/{name}/yaml")
async def get_runbook_yaml(name: str = Path(...)):
    """Return raw YAML content for the runbook editor."""
    import re
    runbooks_dir = os.path.join(os.getcwd(), "runbooks")
    # Find the file by name or stem
    for fname in os.listdir(runbooks_dir) if os.path.isdir(runbooks_dir) else []:
        if fname.endswith(".yml"):
            path = os.path.join(runbooks_dir, fname)
            try:
                import yaml as _yaml
                with open(path) as f:
                    data = _yaml.safe_load(f)
                if data and data.get("name") == name:
                    with open(path) as f:
                        raw = f.read()
                    return Response(content=raw, media_type="text/plain")
            except Exception:
                continue
    raise HTTPException(status_code=404, detail=f"Runbook '{name}' not found")


@app.post("/runbooks")
async def create_runbook(body: dict[str, Any] = Body(...)):
    """
    Create a new runbook YAML file.
    Body: { yaml: "<yaml string>" }
    The 'name' field inside the YAML determines the filename.
    Returns 409 if a runbook with that name already exists.
    """
    import yaml as _yaml
    raw_yaml = body.get("yaml", "")
    if not raw_yaml:
        raise HTTPException(status_code=422, detail="yaml field is required")

    try:
        parsed = _yaml.safe_load(raw_yaml)
    except _yaml.YAMLError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid YAML: {exc}")

    if not isinstance(parsed, dict):
        raise HTTPException(status_code=422, detail="YAML must be a mapping")

    name = parsed.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="YAML must include a 'name' field")

    runbooks_dir = os.path.join(os.getcwd(), "runbooks")
    if not os.path.isdir(runbooks_dir):
        raise HTTPException(status_code=500, detail="Runbooks directory not found")

    # Reject if a runbook with this name already exists
    for fname in os.listdir(runbooks_dir):
        if fname.endswith(".yml"):
            path = os.path.join(runbooks_dir, fname)
            try:
                with open(path) as f:
                    data = _yaml.safe_load(f)
                if data and data.get("name") == name:
                    raise HTTPException(
                        status_code=409,
                        detail=f"Runbook '{name}' already exists — use PUT to update it",
                    )
            except HTTPException:
                raise
            except Exception:
                continue

    target_path = os.path.join(runbooks_dir, f"{name.lower().replace(' ', '_')}.yml")
    try:
        with open(target_path, "w") as f:
            f.write(raw_yaml)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to write runbook: {exc}")

    logger.info("Runbook '%s' created via API", name)
    return {"created": name, "path": os.path.basename(target_path)}


@app.put("/runbooks/{name}")
async def update_runbook(
    name: str = Path(...),
    body: dict[str, Any] = Body(...),
):
    """
    Update a runbook's YAML file.
    Body: { yaml: "<yaml string>" }
    """
    import yaml as _yaml
    raw_yaml = body.get("yaml", "")
    if not raw_yaml:
        raise HTTPException(status_code=422, detail="yaml field is required")

    # Validate YAML + require name field
    try:
        parsed = _yaml.safe_load(raw_yaml)
    except _yaml.YAMLError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid YAML: {exc}")

    if not isinstance(parsed, dict):
        raise HTTPException(status_code=422, detail="YAML must be a mapping")

    if parsed.get("name") != name:
        raise HTTPException(
            status_code=422,
            detail=f"YAML 'name' field must match URL ({name})",
        )

    runbooks_dir = os.path.join(os.getcwd(), "runbooks")
    if not os.path.isdir(runbooks_dir):
        raise HTTPException(status_code=500, detail="Runbooks directory not found")

    # Find existing file or use name as stem
    target_path: str | None = None
    for fname in os.listdir(runbooks_dir):
        if fname.endswith(".yml"):
            path = os.path.join(runbooks_dir, fname)
            try:
                with open(path) as f:
                    data = _yaml.safe_load(f)
                if data and data.get("name") == name:
                    target_path = path
                    break
            except Exception:
                continue

    if target_path is None:
        target_path = os.path.join(runbooks_dir, f"{name.lower().replace(' ', '_')}.yml")

    try:
        with open(target_path, "w") as f:
            f.write(raw_yaml)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to write runbook: {exc}")

    logger.info("Runbook '%s' updated via API", name)
    return {"updated": name, "path": os.path.basename(target_path)}


# ─── Simulate Endpoint ────────────────────────────────────────────────────────

@app.post("/simulate", response_model=WebhookResponse)
async def simulate_alert(
    payload: AlertmanagerWebhook,
    session: AsyncSession = Depends(get_session),
):
    """Simulate in DRY_RUN mode — same as webhook but sets DRY_RUN env."""
    os.environ["APPROVAL_MODE"] = "DRY_RUN"
    return await receive_webhook(payload, session)


# ─── Health Endpoint ──────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
async def health_check():
    llm_backend = os.environ.get("LLM_BACKEND", "ollama").lower()
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

    prometheus_status = "unreachable"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{PROMETHEUS_URL}/-/healthy", timeout=3.0)
            if resp.status_code == 200:
                prometheus_status = "reachable"
    except Exception:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": "1"}, timeout=3.0)
                if resp.status_code == 200:
                    prometheus_status = "reachable"
        except Exception as e:
            logger.debug(f"Prometheus health check failed: {e}")

    # Check Redis
    redis_status = "unreachable"
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(REDIS_URL, socket_connect_timeout=2)
        await r.ping()
        await r.aclose()
        redis_status = "reachable"
    except Exception as e:
        logger.debug(f"Redis health check failed: {e}")

    overall = "healthy"
    if llm_status == "unreachable" or redis_status == "unreachable":
        overall = "degraded"

    return HealthResponse(
        status=overall,
        claude_api=llm_status,
        prometheus=prometheus_status,
        queue_depth=0,
        active_workers=0,
        incidents_processed=0,
        redis=redis_status,
    )
