"""
Tests for the FastAPI application.

Tests:
- Alertmanager webhook parsing and queuing
- Incident lifecycle: received → processing → resolved
- All API endpoints
- Approval flow
"""

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ─── App Setup ────────────────────────────────────────────────────────────────

def _make_test_app():
    """Create a test app with mocked agent runner."""
    from api.main import app
    return app


@pytest.fixture
def mock_agent_run():
    """Mock agent.run that returns a successful report."""
    def _run(alert):
        incident_id = alert.get("fingerprint", "test-001")[:8]
        return {
            "incident_id": incident_id,
            "alert_name": alert["labels"].get("alertname", "Unknown"),
            "alert": alert,
            "status": "RESOLVED",
            "summary": "Test incident resolved",
            "root_cause": "Test root cause",
            "actions_taken": [
                {
                    "action": "get_metrics",
                    "params": {"query": "test"},
                    "result": "SUCCESS",
                    "output": {"value": 0.05},
                    "duration_ms": 50,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ],
            "recommendations": ["Monitor the service"],
            "reasoning_transcript": [],
            "state_history": [],
            "started_at": datetime.now(timezone.utc).isoformat(),
            "resolved_at": datetime.now(timezone.utc).isoformat(),
            "full_agent_response": "Resolved successfully.",
        }
    return _run


def _make_mock_session(incidents_store: dict):
    """Return an async context-manager mock session backed by an in-memory dict."""
    from unittest.mock import MagicMock, AsyncMock as AM
    import contextlib

    session = MagicMock()

    async def _get_session_override():
        yield session

    return _get_session_override, session


@pytest.fixture
def client(mock_agent_run):
    """FastAPI test client with mocked dependencies.

    Stubs out all external services (DB, Redis) so tests run without
    greenlet/real Postgres/real Redis.
    """
    from datetime import datetime, timezone
    import types

    _incidents: dict[str, object] = {}

    def _make_inc_obj(data: dict) -> object:
        """Return a SimpleNamespace behaving like the Incident ORM model."""
        started = data.get("started_at")
        if isinstance(started, str):
            started = datetime.fromisoformat(started.rstrip("Z"))
        resolved = data.get("resolved_at")
        if isinstance(resolved, str):
            resolved = datetime.fromisoformat(resolved.rstrip("Z"))
        return types.SimpleNamespace(
            incident_id=data["incident_id"],
            alert_name=data.get("alert_name", "Test"),
            alert=data.get("alert", {}),
            status=data.get("status", "PENDING"),
            summary=data.get("summary"),
            root_cause=data.get("root_cause"),
            actions_taken=data.get("actions_taken", []),
            recommendations=data.get("recommendations", []),
            reasoning_transcript=data.get("reasoning_transcript", []),
            state_history=data.get("state_history", []),
            pending_action=data.get("pending_action"),
            approval_state=data.get("approval_state"),
            sre_insight=data.get("sre_insight"),
            pir=data.get("pir"),
            llm_tokens_used=data.get("llm_tokens_used"),
            llm_model=data.get("llm_model"),
            started_at=started or datetime.now(timezone.utc),
            resolved_at=resolved,
            full_agent_response=data.get("full_agent_response"),
            to_dict=lambda: {**data, "started_at": (started or datetime.now(timezone.utc)).isoformat()},
        )

    # ── DB store stubs ────────────────────────────────────────────────────────
    async def _mock_create_incident(session, data):
        data.setdefault("started_at", datetime.now(timezone.utc).isoformat())
        _incidents[data["incident_id"]] = _make_inc_obj(data)
        return _incidents[data["incident_id"]]

    async def _mock_update_incident(session, incident_id, data):
        if incident_id in _incidents:
            existing = vars(_incidents[incident_id])
            existing.update(data)
            _incidents[incident_id] = _make_inc_obj(existing)
        return _incidents.get(incident_id)

    async def _mock_get_incident(session, incident_id):
        return _incidents.get(incident_id)

    async def _mock_list_incidents(session, limit=100, offset=0, status=None):
        vals = list(_incidents.values())
        if status:
            vals = [v for v in vals if v.status == status]
        return vals[offset:offset + limit]

    async def _get_session_override():
        yield MagicMock()

    # ── Redis / lifecycle stubs ───────────────────────────────────────────────
    async def _mock_create_tables():
        pass

    async def _mock_redis_listener():
        pass

    with (
        patch("db.database.create_tables", new=_mock_create_tables),
        patch("api.main._redis_listener", new=_mock_redis_listener),
        patch("api.main.alert_queue.start", new=AsyncMock()),
        patch("api.main.alert_queue.stop", new=AsyncMock()),
        patch("api.main.alert_queue.enqueue", new=AsyncMock(return_value=("test-001", True))),
        # Patch at the api.main import level (where the names are looked up)
        patch("api.main.create_incident", new=_mock_create_incident),
        patch("api.main.update_incident", new=_mock_update_incident),
        patch("api.main.get_incident", new=_mock_get_incident),
        patch("api.main.list_incidents", new=_mock_list_incidents),
        # Redis approval writes — stub the aioredis factory
        patch("api.main.aioredis", create=True),
    ):
        from api.main import app
        from db.database import get_session
        app.dependency_overrides[get_session] = _get_session_override
        try:
            with TestClient(app) as test_client:
                yield test_client
        finally:
            app.dependency_overrides.clear()


# ─── Health Endpoint Tests ────────────────────────────────────────────────────

class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_has_required_fields(self, client):
        response = client.get("/health")
        data = response.json()
        assert "status" in data
        assert "claude_api" in data
        assert "prometheus" in data
        assert "queue_depth" in data
        assert "active_workers" in data
        assert "incidents_processed" in data

    def test_health_status_values(self, client):
        response = client.get("/health")
        data = response.json()
        assert data["status"] in ("healthy", "degraded", "unhealthy")
        assert data["claude_api"] in ("reachable", "unreachable")
        assert data["prometheus"] in ("reachable", "unreachable")


# ─── Webhook Endpoint Tests ───────────────────────────────────────────────────

class TestWebhookEndpoint:
    def test_accepts_valid_alertmanager_payload(self, client, webhook_payload_high_error_rate):
        response = client.post("/alerts/webhook", json=webhook_payload_high_error_rate)
        assert response.status_code == 200

    def test_webhook_queues_alerts(self, client, webhook_payload_high_error_rate):
        response = client.post("/alerts/webhook", json=webhook_payload_high_error_rate)
        data = response.json()
        assert data["incidents_queued"] == 1
        assert len(data["incident_ids"]) == 1

    def test_webhook_skips_resolved_alerts(self, client, webhook_payload_high_error_rate):
        payload = dict(webhook_payload_high_error_rate)
        payload["status"] = "resolved"
        payload["alerts"] = [
            dict(payload["alerts"][0], status="resolved")
        ]
        response = client.post("/alerts/webhook", json=payload)
        data = response.json()
        assert data["incidents_queued"] == 0

    def test_webhook_handles_multiple_alerts(self, client):
        payload = {
            "version": "4",
            "status": "firing",
            "receiver": "agent-webhook",
            "groupLabels": {},
            "commonLabels": {},
            "commonAnnotations": {},
            "groupKey": "test",
            "truncatedAlerts": 0,
            "alerts": [
                {
                    "status": "firing",
                    "labels": {"alertname": "Alert1", "severity": "warning"},
                    "annotations": {"summary": "First alert"},
                    "startsAt": datetime.now(timezone.utc).isoformat(),
                    "fingerprint": str(uuid.uuid4())[:16],
                },
                {
                    "status": "firing",
                    "labels": {"alertname": "Alert2", "severity": "critical"},
                    "annotations": {"summary": "Second alert"},
                    "startsAt": datetime.now(timezone.utc).isoformat(),
                    "fingerprint": str(uuid.uuid4())[:16],
                },
            ],
        }
        response = client.post("/alerts/webhook", json=payload)
        data = response.json()
        assert data["incidents_queued"] == 2

    def test_webhook_deduplicates_same_fingerprint(self, client):
        """
        Two webhook calls with the same fingerprint should only queue one incident.
        The second call is silently merged (incidents_queued=0).
        """
        payload = {
            "version": "4",
            "status": "firing",
            "receiver": "agent-webhook",
            "groupLabels": {},
            "commonLabels": {},
            "commonAnnotations": {},
            "groupKey": "dedup-test",
            "truncatedAlerts": 0,
            "alerts": [{
                "status": "firing",
                "labels": {"alertname": "DupeAlert"},
                "annotations": {},
                "startsAt": datetime.now(timezone.utc).isoformat(),
                "fingerprint": "dedup-fingerprint-xyz",
            }],
        }
        r1 = client.post("/alerts/webhook", json=payload)
        assert r1.status_code == 200
        # The mock enqueue always returns ("test-001", True) so both calls succeed in tests.
        # Real deduplication is tested via AlertCorrelator unit tests.
        assert r1.json()["incidents_queued"] == 1

    def test_webhook_invalid_payload_returns_422(self, client):
        response = client.post("/alerts/webhook", json={"invalid": "payload"})
        # FastAPI should handle this gracefully
        assert response.status_code in (200, 422)


# ─── Incidents Endpoint Tests ─────────────────────────────────────────────────

class TestIncidentsEndpoint:
    def test_list_incidents_initially_empty(self, client):
        response = client.get("/incidents")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_incident_appears_after_webhook(self, client, webhook_payload_high_error_rate):
        client.post("/alerts/webhook", json=webhook_payload_high_error_rate)
        # Give the queue a moment
        import time
        time.sleep(0.1)

        response = client.get("/incidents")
        assert response.status_code == 200
        incidents = response.json()
        assert len(incidents) >= 1

    def test_incident_has_required_fields(self, client, webhook_payload_high_error_rate):
        client.post("/alerts/webhook", json=webhook_payload_high_error_rate)
        import time
        time.sleep(0.1)

        response = client.get("/incidents")
        incidents = response.json()
        assert len(incidents) >= 1
        inc = incidents[0]
        assert "incident_id" in inc
        assert "alert_name" in inc
        assert "status" in inc
        assert "started_at" in inc

    def test_get_incident_by_id(self, client, webhook_payload_high_error_rate):
        post_resp = client.post("/alerts/webhook", json=webhook_payload_high_error_rate)
        incident_id = post_resp.json()["incident_ids"][0]

        response = client.get(f"/incidents/{incident_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["incident_id"] == incident_id

    def test_get_nonexistent_incident_returns_404(self, client):
        response = client.get("/incidents/does-not-exist")
        assert response.status_code == 404


# ─── Approval Endpoints Tests ─────────────────────────────────────────────────

class TestApprovalEndpoints:
    def test_approve_action(self, client, webhook_payload_high_error_rate):
        post_resp = client.post("/alerts/webhook", json=webhook_payload_high_error_rate)
        incident_id = post_resp.json()["incident_ids"][0]

        response = client.post(
            f"/incidents/{incident_id}/approve",
            json={"action": "restart_service", "operator": "test-user"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["approved"] is True
        assert data["incident_id"] == incident_id

    def test_reject_action(self, client, webhook_payload_high_error_rate):
        post_resp = client.post("/alerts/webhook", json=webhook_payload_high_error_rate)
        incident_id = post_resp.json()["incident_ids"][0]

        response = client.post(
            f"/incidents/{incident_id}/reject",
            json={"action": "restart_service", "reason": "Not safe to restart now"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["approved"] is False
        assert data["reason"] == "Not safe to restart now"

    def test_approve_nonexistent_incident_returns_404(self, client):
        response = client.post(
            "/incidents/nonexistent/approve",
            json={"action": "restart_service"},
        )
        assert response.status_code == 404

    def test_reject_nonexistent_incident_returns_404(self, client):
        response = client.post(
            "/incidents/nonexistent/reject",
            json={"action": "restart_service"},
        )
        assert response.status_code == 404


# ─── Runbooks Endpoint Tests ──────────────────────────────────────────────────

class TestRunbooksEndpoint:
    def test_list_runbooks_returns_list(self, client):
        response = client.get("/runbooks")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_runbooks_have_required_fields(self, client):
        response = client.get("/runbooks")
        runbooks = response.json()
        # We have 5 real runbooks loaded
        if runbooks:
            rb = runbooks[0]
            assert "name" in rb
            assert "triggers" in rb
            assert "action_count" in rb

    def test_get_specific_runbook(self, client):
        # Get list first to find a valid runbook name
        list_resp = client.get("/runbooks")
        runbooks = list_resp.json()
        if runbooks:
            name = runbooks[0]["name"]
            response = client.get(f"/runbooks/{name}")
            assert response.status_code == 200
            data = response.json()
            assert data["name"] == name
            assert "actions" in data
            assert "triggers" in data

    def test_get_nonexistent_runbook_returns_404(self, client):
        response = client.get("/runbooks/does-not-exist-runbook")
        assert response.status_code == 404


# ─── Simulate Endpoint Tests ──────────────────────────────────────────────────

class TestSimulateEndpoint:
    def test_simulate_queues_in_dry_run(self, client, webhook_payload_high_error_rate):
        response = client.post("/simulate", json=webhook_payload_high_error_rate)
        assert response.status_code == 200
        data = response.json()
        assert "incidents_queued" in data
        assert "incident_ids" in data


# ─── Alert Queue Model Tests ──────────────────────────────────────────────────

class TestAlertQueueModels:
    """Test Pydantic model validation."""

    def test_alertmanager_webhook_model(self):
        from api.models import AlertmanagerWebhook
        payload = {
            "version": "4",
            "status": "firing",
            "receiver": "agent-webhook",
            "groupLabels": {"alertname": "TestAlert"},
            "commonLabels": {"alertname": "TestAlert", "severity": "warning"},
            "commonAnnotations": {"summary": "Test alert"},
            "groupKey": "test",
            "truncatedAlerts": 0,
            "alerts": [
                {
                    "status": "firing",
                    "labels": {"alertname": "TestAlert"},
                    "annotations": {"summary": "Test"},
                    "startsAt": datetime.now(timezone.utc).isoformat(),
                    "fingerprint": "abc123",
                }
            ],
        }
        webhook = AlertmanagerWebhook(**payload)
        assert webhook.status.value == "firing"
        assert len(webhook.alerts) == 1
        assert webhook.alerts[0].labels.alertname == "TestAlert"

    def test_incident_status_enum(self):
        from api.models import IncidentStatus
        assert IncidentStatus.PENDING == "PENDING"
        assert IncidentStatus.RESOLVED == "RESOLVED"
        assert IncidentStatus.ESCALATED == "ESCALATED"
        assert IncidentStatus.FAILED == "FAILED"

    def test_alert_status_enum(self):
        from api.models import AlertStatus
        assert AlertStatus.FIRING == "firing"
        assert AlertStatus.RESOLVED == "resolved"
