from __future__ import annotations

"""
Tests for db/incident_store.py

Since the ORM models use JSONB (PostgreSQL-specific), we mock the SQLAlchemy
session rather than standing up a real DB. This keeps tests fast and dependency-free.

Tests:
- create_incident: creates row with correct fields
- get_incident: returns None for missing, incident for known id
- update_incident: updates specified fields, sets updated_at
- list_incidents: returns list ordered by started_at desc
- get_mttr_stats: computes totals, auto_resolution_rate, MTTR, by_alert_name
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from db.incident_store import (
    create_incident,
    get_incident,
    get_mttr_stats,
    list_incidents,
    update_incident,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _make_incident_row(
    incident_id: str = "test-001",
    alert_name: str = "HighErrorRate",
    status: str = "PENDING",
    resolved_at: datetime | None = None,
) -> MagicMock:
    row = MagicMock()
    row.incident_id = incident_id
    row.alert_name = alert_name
    row.status = status
    row.started_at = _utcnow() - timedelta(minutes=5)
    row.resolved_at = resolved_at
    row.summary = None
    row.root_cause = None
    row.actions_taken = []
    row.recommendations = []
    row.reasoning_transcript = []
    row.state_history = []
    row.pir = None
    row.pending_action = None
    row.approval_state = None
    row.llm_tokens_used = None
    row.llm_model = None
    row.full_agent_response = None
    row.to_dict.return_value = {
        "incident_id": incident_id,
        "alert_name": alert_name,
        "status": status,
    }
    return row


def _mock_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock()
    return session


# ─── create_incident ─────────────────────────────────────────────────────────

class TestCreateIncident:
    def test_adds_and_commits(self):
        session = _mock_session()
        session.refresh.side_effect = lambda row: None

        asyncio.get_event_loop().run_until_complete(
            create_incident(session, {
                "incident_id": "inc-001",
                "alert_name": "HighErrorRate",
                "alert": {"labels": {}},
                "status": "PENDING",
            })
        )

        assert session.add.called
        assert session.commit.called

    def test_uses_provided_status(self):
        session = _mock_session()
        added_rows = []

        def _add(row):
            added_rows.append(row)

        session.add.side_effect = _add
        session.refresh.side_effect = lambda row: None

        asyncio.get_event_loop().run_until_complete(
            create_incident(session, {
                "incident_id": "inc-002",
                "alert_name": "HighLatency",
                "status": "PROCESSING",
            })
        )

        assert len(added_rows) == 1
        assert added_rows[0].status == "PROCESSING"

    def test_defaults_status_to_pending(self):
        session = _mock_session()
        added_rows = []
        session.add.side_effect = lambda row: added_rows.append(row)
        session.refresh.side_effect = lambda row: None

        asyncio.get_event_loop().run_until_complete(
            create_incident(session, {
                "incident_id": "inc-003",
                "alert_name": "ServiceDown",
            })
        )

        assert added_rows[0].status == "PENDING"

    def test_sets_started_at(self):
        session = _mock_session()
        added_rows = []
        session.add.side_effect = lambda row: added_rows.append(row)
        session.refresh.side_effect = lambda row: None

        asyncio.get_event_loop().run_until_complete(
            create_incident(session, {
                "incident_id": "inc-004",
                "alert_name": "ServiceDown",
            })
        )

        assert added_rows[0].started_at is not None
        assert isinstance(added_rows[0].started_at, datetime)


# ─── get_incident ────────────────────────────────────────────────────────────

class TestGetIncident:
    def test_returns_incident_when_found(self):
        session = _mock_session()
        mock_row = _make_incident_row("inc-001")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_row
        session.execute.return_value = mock_result

        result = asyncio.get_event_loop().run_until_complete(
            get_incident(session, "inc-001")
        )

        assert result is mock_row

    def test_returns_none_for_missing(self):
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        result = asyncio.get_event_loop().run_until_complete(
            get_incident(session, "does-not-exist")
        )

        assert result is None


# ─── update_incident ─────────────────────────────────────────────────────────

class TestUpdateIncident:
    def test_calls_execute_and_commit(self):
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _make_incident_row("inc-001")
        session.execute.return_value = mock_result

        asyncio.get_event_loop().run_until_complete(
            update_incident(session, "inc-001", {"status": "RESOLVED"})
        )

        assert session.execute.called
        assert session.commit.called

    def test_always_sets_updated_at(self):
        """update_incident should inject updated_at into the fields dict."""
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _make_incident_row()
        session.execute.return_value = mock_result

        fields = {"status": "RESOLVED"}
        asyncio.get_event_loop().run_until_complete(
            update_incident(session, "inc-001", fields)
        )

        # updated_at should have been injected into fields before execute
        assert "updated_at" in fields

    def test_returns_updated_incident(self):
        """Should return the refreshed incident row."""
        session = _mock_session()
        mock_row = _make_incident_row("inc-001", status="RESOLVED")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_row
        session.execute.return_value = mock_result

        result = asyncio.get_event_loop().run_until_complete(
            update_incident(session, "inc-001", {"status": "RESOLVED"})
        )

        assert result is mock_row


# ─── list_incidents ───────────────────────────────────────────────────────────

class TestListIncidents:
    def test_returns_list(self):
        session = _mock_session()
        rows = [
            _make_incident_row("inc-001"),
            _make_incident_row("inc-002"),
        ]
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = rows
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        session.execute.return_value = mock_result

        result = asyncio.get_event_loop().run_until_complete(
            list_incidents(session)
        )

        assert isinstance(result, list)
        assert len(result) == 2

    def test_returns_empty_list_when_no_incidents(self):
        session = _mock_session()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        session.execute.return_value = mock_result

        result = asyncio.get_event_loop().run_until_complete(
            list_incidents(session)
        )

        assert result == []


# ─── get_mttr_stats ───────────────────────────────────────────────────────────

class TestGetMttrStats:
    def _setup_session(self, incidents: list) -> AsyncMock:
        session = _mock_session()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = incidents
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        session.execute.return_value = mock_result
        return session

    def test_empty_db_returns_zeros(self):
        session = self._setup_session([])
        stats = asyncio.get_event_loop().run_until_complete(get_mttr_stats(session))

        assert stats["total"] == 0
        assert stats["resolved"] == 0
        assert stats["escalated"] == 0
        assert stats["failed"] == 0
        assert stats["auto_resolution_rate"] == 0
        assert stats["mttr_seconds"] is None

    def test_counts_by_status(self):
        now = _utcnow()
        incidents = [
            _make_incident_row("i1", status="RESOLVED", resolved_at=now),
            _make_incident_row("i2", status="RESOLVED", resolved_at=now),
            _make_incident_row("i3", status="ESCALATED"),
            _make_incident_row("i4", status="FAILED"),
            _make_incident_row("i5", status="PROCESSING"),
        ]
        session = self._setup_session(incidents)
        stats = asyncio.get_event_loop().run_until_complete(get_mttr_stats(session))

        assert stats["total"] == 5
        assert stats["resolved"] == 2
        assert stats["escalated"] == 1
        assert stats["failed"] == 1

    def test_auto_resolution_rate_calculation(self):
        now = _utcnow()
        incidents = [
            _make_incident_row("i1", status="RESOLVED", resolved_at=now),
            _make_incident_row("i2", status="RESOLVED", resolved_at=now),
            _make_incident_row("i3", status="ESCALATED"),
            _make_incident_row("i4", status="FAILED"),
        ]
        session = self._setup_session(incidents)
        stats = asyncio.get_event_loop().run_until_complete(get_mttr_stats(session))

        assert stats["auto_resolution_rate"] == 50.0

    def test_mttr_calculated_for_resolved(self):
        now = _utcnow()
        row = _make_incident_row("i1", status="RESOLVED", resolved_at=now)
        row.started_at = now - timedelta(minutes=10)  # 600 seconds
        row.resolved_at = now

        session = self._setup_session([row])
        stats = asyncio.get_event_loop().run_until_complete(get_mttr_stats(session))

        assert stats["mttr_seconds"] is not None
        assert stats["mttr_seconds"] == pytest.approx(600.0, abs=5.0)

    def test_by_alert_name_counts(self):
        now = _utcnow()
        incidents = [
            _make_incident_row("i1", alert_name="HighErrorRate", status="RESOLVED", resolved_at=now),
            _make_incident_row("i2", alert_name="HighErrorRate", status="RESOLVED", resolved_at=now),
            _make_incident_row("i3", alert_name="ServiceDown", status="ESCALATED"),
        ]
        session = self._setup_session(incidents)
        stats = asyncio.get_event_loop().run_until_complete(get_mttr_stats(session))

        assert stats["by_alert_name"]["HighErrorRate"] == 2
        assert stats["by_alert_name"]["ServiceDown"] == 1
