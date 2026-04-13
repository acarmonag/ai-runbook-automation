from __future__ import annotations

"""
Tests for worker/jobs.py and worker/pir.py

Tests:
- process_alert sets incident to PROCESSING before running agent
- process_alert persists RESOLVED status after successful run
- process_alert persists FAILED status when agent raises
- PIR is generated after RESOLVED incident
- PIR is NOT generated for ESCALATED or FAILED incident
- Correlation key is deleted after job completion
- Prometheus metric recording doesn't crash on error
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_alert(alertname: str = "HighErrorRate", service: str = "api") -> dict:
    return {
        "labels": {"alertname": alertname, "service": service, "severity": "critical"},
        "annotations": {"summary": f"{alertname} on {service}"},
        "fingerprint": f"{service}-{alertname}",
    }


def _make_report(status: str = "RESOLVED") -> dict:
    return {
        "incident_id": "test-001",
        "alert_name": "HighErrorRate",
        "alert": _make_alert(),
        "status": status,
        "summary": "High error rate resolved by restart",
        "root_cause": "Connection pool exhaustion",
        "actions_taken": [
            {
                "action": "restart_service",
                "params": {"service": "api"},
                "result": "SUCCESS",
                "output": "Restarted",
                "duration_ms": 3000,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ],
        "recommendations": ["Monitor connection pool"],
        "reasoning_transcript": [],
        "state_history": [],
        "started_at": datetime.now(timezone.utc).isoformat(),
        "resolved_at": datetime.now(timezone.utc).isoformat(),
        "full_agent_response": "",
        "llm_tokens_used": 0,
        "llm_model": "test",
    }


def _make_ctx() -> dict:
    """Minimal ARQ job context."""
    mock_redis = AsyncMock()
    mock_redis.delete = AsyncMock()
    mock_redis.publish = AsyncMock()
    return {"redis": mock_redis}


# ─── process_alert — happy path ───────────────────────────────────────────────

class TestProcessAlertHappyPath:
    def test_sets_processing_status_before_agent_runs(self):
        """Incident must transition to PROCESSING before agent.run() is called."""
        ctx = _make_ctx()
        incident_id = "test-001"
        alert = _make_alert()
        report = _make_report("RESOLVED")

        calls = []

        async def fake_update(session, id_, fields):
            calls.append(fields.get("status"))
            return MagicMock()

        async def fake_get(session, id_):
            return MagicMock()  # existing row

        mock_agent = MagicMock()
        mock_agent.run.return_value = report

        with (
            patch("worker.jobs.AsyncSessionLocal") as mock_session_factory,
            patch("worker.jobs.get_incident", side_effect=fake_get),
            patch("worker.jobs.update_incident", side_effect=fake_update),
            patch("worker.jobs.create_incident", new=AsyncMock()),
            patch("worker.jobs.publish_incident_update", new=AsyncMock()),
            patch("worker.jobs.build_default_registry", return_value=MagicMock()),
            patch("worker.jobs.RunbookRegistry", return_value=MagicMock()),
            patch("worker.jobs.ApprovalGate", return_value=MagicMock()),
            patch("worker.jobs.SREAgent", return_value=mock_agent),
            patch("worker.jobs.generate_pir", new=AsyncMock()),
            patch("worker.jobs._delete_correlation_key", new=AsyncMock()),
            patch("worker.jobs._reset_mock_prometheus", new=AsyncMock()),
        ):
            # Set up session context manager
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session_factory.return_value = mock_session

            asyncio.get_event_loop().run_until_complete(
                __import__("worker.jobs", fromlist=["process_alert"]).process_alert(
                    ctx, incident_id, alert
                )
            )

        assert "PROCESSING" in calls

    def test_persists_resolved_status(self):
        """Final status from agent report must be persisted."""
        ctx = _make_ctx()
        incident_id = "test-002"
        alert = _make_alert()
        report = _make_report("RESOLVED")

        final_status_calls = []

        async def fake_update(session, id_, fields):
            if "summary" in fields:  # final update
                final_status_calls.append(fields.get("status"))
            return MagicMock()

        mock_agent = MagicMock()
        mock_agent.run.return_value = report

        with (
            patch("worker.jobs.AsyncSessionLocal") as mock_sf,
            patch("worker.jobs.get_incident", new=AsyncMock(return_value=MagicMock())),
            patch("worker.jobs.update_incident", side_effect=fake_update),
            patch("worker.jobs.create_incident", new=AsyncMock()),
            patch("worker.jobs.publish_incident_update", new=AsyncMock()),
            patch("worker.jobs.build_default_registry", return_value=MagicMock()),
            patch("worker.jobs.RunbookRegistry", return_value=MagicMock()),
            patch("worker.jobs.ApprovalGate", return_value=MagicMock()),
            patch("worker.jobs.SREAgent", return_value=mock_agent),
            patch("worker.jobs.generate_pir", new=AsyncMock()),
            patch("worker.jobs._delete_correlation_key", new=AsyncMock()),
            patch("worker.jobs._reset_mock_prometheus", new=AsyncMock()),
        ):
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_sf.return_value = mock_session

            asyncio.get_event_loop().run_until_complete(
                __import__("worker.jobs", fromlist=["process_alert"]).process_alert(
                    ctx, incident_id, alert
                )
            )

        assert "RESOLVED" in final_status_calls

    def test_publishes_websocket_update(self):
        """publish_incident_update must be called with the final status."""
        ctx = _make_ctx()
        publish_calls = []

        async def fake_publish(redis, incident_id, status):
            publish_calls.append(status)

        mock_agent = MagicMock()
        mock_agent.run.return_value = _make_report("RESOLVED")

        with (
            patch("worker.jobs.AsyncSessionLocal") as mock_sf,
            patch("worker.jobs.get_incident", new=AsyncMock(return_value=MagicMock())),
            patch("worker.jobs.update_incident", new=AsyncMock(return_value=MagicMock())),
            patch("worker.jobs.create_incident", new=AsyncMock()),
            patch("worker.jobs.publish_incident_update", side_effect=fake_publish),
            patch("worker.jobs.build_default_registry", return_value=MagicMock()),
            patch("worker.jobs.RunbookRegistry", return_value=MagicMock()),
            patch("worker.jobs.ApprovalGate", return_value=MagicMock()),
            patch("worker.jobs.SREAgent", return_value=mock_agent),
            patch("worker.jobs.generate_pir", new=AsyncMock()),
            patch("worker.jobs._delete_correlation_key", new=AsyncMock()),
            patch("worker.jobs._reset_mock_prometheus", new=AsyncMock()),
        ):
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_sf.return_value = mock_session

            asyncio.get_event_loop().run_until_complete(
                __import__("worker.jobs", fromlist=["process_alert"]).process_alert(
                    ctx, "test-003", _make_alert()
                )
            )

        assert "PROCESSING" in publish_calls
        assert "RESOLVED" in publish_calls


# ─── process_alert — failure path ─────────────────────────────────────────────

class TestProcessAlertFailurePath:
    def test_persists_failed_when_agent_raises(self):
        """If agent.run() raises, status must be set to FAILED and re-raise."""
        ctx = _make_ctx()
        failed_calls = []

        async def fake_update(session, id_, fields):
            if fields.get("status") == "FAILED":
                failed_calls.append(True)
            return MagicMock()

        mock_agent = MagicMock()
        mock_agent.run.side_effect = RuntimeError("LLM connection refused")

        with (
            patch("worker.jobs.AsyncSessionLocal") as mock_sf,
            patch("worker.jobs.get_incident", new=AsyncMock(return_value=MagicMock())),
            patch("worker.jobs.update_incident", side_effect=fake_update),
            patch("worker.jobs.create_incident", new=AsyncMock()),
            patch("worker.jobs.publish_incident_update", new=AsyncMock()),
            patch("worker.jobs.build_default_registry", return_value=MagicMock()),
            patch("worker.jobs.RunbookRegistry", return_value=MagicMock()),
            patch("worker.jobs.ApprovalGate", return_value=MagicMock()),
            patch("worker.jobs.SREAgent", return_value=mock_agent),
        ):
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_sf.return_value = mock_session

            with pytest.raises(RuntimeError, match="LLM connection refused"):
                asyncio.get_event_loop().run_until_complete(
                    __import__("worker.jobs", fromlist=["process_alert"]).process_alert(
                        ctx, "test-004", _make_alert()
                    )
                )

        assert len(failed_calls) > 0

    def test_creates_incident_when_no_existing(self):
        """If no existing incident row, create_incident should be called."""
        ctx = _make_ctx()
        create_calls = []

        async def fake_create(session, data):
            create_calls.append(data)
            return MagicMock()

        mock_agent = MagicMock()
        mock_agent.run.return_value = _make_report("RESOLVED")

        with (
            patch("worker.jobs.AsyncSessionLocal") as mock_sf,
            patch("worker.jobs.get_incident", new=AsyncMock(return_value=None)),  # no existing
            patch("worker.jobs.update_incident", new=AsyncMock(return_value=MagicMock())),
            patch("worker.jobs.create_incident", side_effect=fake_create),
            patch("worker.jobs.publish_incident_update", new=AsyncMock()),
            patch("worker.jobs.build_default_registry", return_value=MagicMock()),
            patch("worker.jobs.RunbookRegistry", return_value=MagicMock()),
            patch("worker.jobs.ApprovalGate", return_value=MagicMock()),
            patch("worker.jobs.SREAgent", return_value=mock_agent),
            patch("worker.jobs.generate_pir", new=AsyncMock()),
            patch("worker.jobs._delete_correlation_key", new=AsyncMock()),
            patch("worker.jobs._reset_mock_prometheus", new=AsyncMock()),
        ):
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_sf.return_value = mock_session

            asyncio.get_event_loop().run_until_complete(
                __import__("worker.jobs", fromlist=["process_alert"]).process_alert(
                    ctx, "test-005", _make_alert()
                )
            )

        assert len(create_calls) > 0


# ─── PIR generation ───────────────────────────────────────────────────────────

class TestPirGeneration:
    def _run_job(self, status: str):
        ctx = _make_ctx()
        pir_calls = []

        async def fake_generate_pir(incident_id, report):
            pir_calls.append(incident_id)

        mock_agent = MagicMock()
        mock_agent.run.return_value = _make_report(status)

        with (
            patch("worker.jobs.AsyncSessionLocal") as mock_sf,
            patch("worker.jobs.get_incident", new=AsyncMock(return_value=MagicMock())),
            patch("worker.jobs.update_incident", new=AsyncMock(return_value=MagicMock())),
            patch("worker.jobs.create_incident", new=AsyncMock()),
            patch("worker.jobs.publish_incident_update", new=AsyncMock()),
            patch("worker.jobs.build_default_registry", return_value=MagicMock()),
            patch("worker.jobs.RunbookRegistry", return_value=MagicMock()),
            patch("worker.jobs.ApprovalGate", return_value=MagicMock()),
            patch("worker.jobs.SREAgent", return_value=mock_agent),
            patch("worker.jobs.generate_pir", side_effect=fake_generate_pir),
            patch("worker.jobs._delete_correlation_key", new=AsyncMock()),
            patch("worker.jobs._reset_mock_prometheus", new=AsyncMock()),
        ):
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_sf.return_value = mock_session

            asyncio.get_event_loop().run_until_complete(
                __import__("worker.jobs", fromlist=["process_alert"]).process_alert(
                    ctx, "test-pir", _make_alert()
                )
            )

        return pir_calls

    def test_pir_generated_for_resolved(self):
        calls = self._run_job("RESOLVED")
        assert len(calls) == 1

    def test_pir_not_generated_for_escalated(self):
        calls = self._run_job("ESCALATED")
        assert len(calls) == 0

    def test_pir_not_generated_for_failed(self):
        calls = self._run_job("FAILED")
        assert len(calls) == 0


# ─── PIR generator unit tests ─────────────────────────────────────────────────

class TestGeneratePir:
    def test_pir_calls_llm_and_persists(self):
        """generate_pir should call the LLM and write pir field to DB."""
        import json
        pir_updates = []

        async def fake_update(session, id_, fields):
            pir_updates.append(fields)
            return MagicMock()

        mock_backend = MagicMock()
        mock_backend.chat.return_value = MagicMock(
            text=json.dumps({
                "title": "High Error Rate PIR",
                "severity": "P2",
                "root_cause": "DB pool exhaustion",
                "timeline": [],
                "contributing_factors": [],
                "impact": "5 minutes of elevated errors",
                "resolution": "Service restarted",
                "action_items": [],
                "prevention": [],
            })
        )

        with (
            patch("worker.pir.create_backend", return_value=mock_backend),
            patch("worker.pir.AsyncSessionLocal") as mock_sf,
            patch("worker.pir.update_incident", side_effect=fake_update),
        ):
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_sf.return_value = mock_session

            asyncio.get_event_loop().run_until_complete(
                __import__("worker.pir", fromlist=["generate_pir"]).generate_pir(
                    "test-001", _make_report("RESOLVED")
                )
            )

        assert len(pir_updates) == 1
        assert "pir" in pir_updates[0]

    def test_pir_handles_llm_error_gracefully(self):
        """LLM failure during PIR generation must not raise — just log."""
        mock_backend = MagicMock()
        mock_backend.chat.side_effect = RuntimeError("LLM down")

        with patch("worker.pir.create_backend", return_value=mock_backend):
            # Should not raise
            asyncio.get_event_loop().run_until_complete(
                __import__("worker.pir", fromlist=["generate_pir"]).generate_pir(
                    "test-002", _make_report("RESOLVED")
                )
            )

    def test_pir_handles_invalid_json_gracefully(self):
        """If LLM returns invalid JSON, should not raise."""
        mock_backend = MagicMock()
        mock_backend.chat.return_value = MagicMock(text="This is not JSON at all")

        with patch("worker.pir.create_backend", return_value=mock_backend):
            asyncio.get_event_loop().run_until_complete(
                __import__("worker.pir", fromlist=["generate_pir"]).generate_pir(
                    "test-003", _make_report("RESOLVED")
                )
            )


# ─── _delete_correlation_key ─────────────────────────────────────────────────

class TestDeleteCorrelationKey:
    def test_deletes_correct_key(self):
        deleted_keys = []

        async def fake_delete(key):
            deleted_keys.append(key)

        mock_redis = AsyncMock()
        mock_redis.delete = fake_delete
        alert = _make_alert("HighErrorRate", "api")

        asyncio.get_event_loop().run_until_complete(
            __import__("worker.jobs", fromlist=["_delete_correlation_key"])
            ._delete_correlation_key(alert, mock_redis)
        )

        assert len(deleted_keys) == 1
        assert "corr:api:higherrorrate" in deleted_keys[0]

    def test_handles_redis_delete_error(self):
        """Redis delete failure must not raise."""
        mock_redis = AsyncMock()
        mock_redis.delete.side_effect = ConnectionError("Redis down")
        alert = _make_alert()

        asyncio.get_event_loop().run_until_complete(
            __import__("worker.jobs", fromlist=["_delete_correlation_key"])
            ._delete_correlation_key(alert, mock_redis)
        )
