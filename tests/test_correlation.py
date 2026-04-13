from __future__ import annotations

"""
Tests for api/correlation.py — AlertCorrelator

Tests:
- New alert creates a new correlation group
- Duplicate alert (same service+alertname) returns existing incident_id
- Different service creates separate group
- Different alertname creates separate group
- Group key is case-insensitive
- Redis error degrades gracefully (treats alert as new)
- TTL is refreshed on correlated alert
- active_groups returns current state
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.correlation import AlertCorrelator, _CORR_PREFIX


def _alert(alertname: str, service: str = "api") -> dict:
    return {
        "labels": {
            "alertname": alertname,
            "service": service,
            "severity": "critical",
        },
        "annotations": {"summary": f"{alertname} on {service}"},
        "fingerprint": f"{service}-{alertname}",
    }


# ─── _group_key ───────────────────────────────────────────────────────────────

class TestGroupKey:
    def test_key_uses_corr_prefix(self):
        key = AlertCorrelator._group_key(_alert("HighErrorRate", "api"))
        assert key.startswith(_CORR_PREFIX + ":")

    def test_key_includes_service(self):
        key = AlertCorrelator._group_key(_alert("HighErrorRate", "checkout"))
        assert "checkout" in key

    def test_key_includes_alertname(self):
        key = AlertCorrelator._group_key(_alert("HighErrorRate", "api"))
        assert "higherrorrate" in key

    def test_key_is_lowercase(self):
        key = AlertCorrelator._group_key(_alert("HighErrorRate", "API-Service"))
        assert key == key.lower()

    def test_different_services_produce_different_keys(self):
        k1 = AlertCorrelator._group_key(_alert("HighErrorRate", "api"))
        k2 = AlertCorrelator._group_key(_alert("HighErrorRate", "checkout"))
        assert k1 != k2

    def test_different_alertnames_produce_different_keys(self):
        k1 = AlertCorrelator._group_key(_alert("HighErrorRate", "api"))
        k2 = AlertCorrelator._group_key(_alert("HighLatency", "api"))
        assert k1 != k2

    def test_same_alert_same_key(self):
        alert = _alert("ServiceDown", "api")
        assert AlertCorrelator._group_key(alert) == AlertCorrelator._group_key(alert)

    def test_job_label_fallback(self):
        """Falls back to 'job' label when 'service' is absent."""
        alert = {"labels": {"alertname": "CPUSpike", "job": "node-exporter"}}
        key = AlertCorrelator._group_key(alert)
        assert "node-exporter" in key

    def test_unknown_service_fallback(self):
        """Falls back to 'unknown' when neither service nor job is present."""
        alert = {"labels": {"alertname": "SomeAlert"}}
        key = AlertCorrelator._group_key(alert)
        assert "unknown" in key


# ─── get_or_create ────────────────────────────────────────────────────────────

def _make_correlator_with_mock_redis():
    """Return (correlator, mock_redis_client)."""
    mock_redis = AsyncMock()
    correlator = AlertCorrelator(redis_url="redis://mock:6379")
    correlator._client = mock_redis
    return correlator, mock_redis


class TestGetOrCreate:
    def test_new_alert_returns_candidate_id(self):
        """SET NX succeeds → candidate_id is returned (new group)."""
        correlator, mock_redis = _make_correlator_with_mock_redis()
        mock_redis.set.return_value = True  # was_set = True

        result = asyncio.get_event_loop().run_until_complete(
            correlator.get_or_create(_alert("HighErrorRate"), "incident-001")
        )

        assert result == "incident-001"

    def test_duplicate_alert_returns_existing_id(self):
        """SET NX fails (key exists) → get() returns existing incident_id."""
        correlator, mock_redis = _make_correlator_with_mock_redis()
        mock_redis.set.return_value = False  # was_set = False (already exists)
        mock_redis.get.return_value = "incident-001"
        mock_redis.expire.return_value = True

        result = asyncio.get_event_loop().run_until_complete(
            correlator.get_or_create(_alert("HighErrorRate"), "incident-002")
        )

        assert result == "incident-001"

    def test_ttl_refreshed_on_correlated_alert(self):
        """expire() is called when merging into existing group."""
        correlator, mock_redis = _make_correlator_with_mock_redis()
        mock_redis.set.return_value = False
        mock_redis.get.return_value = "incident-001"
        mock_redis.expire.return_value = True

        asyncio.get_event_loop().run_until_complete(
            correlator.get_or_create(_alert("HighErrorRate"), "incident-002")
        )

        mock_redis.expire.assert_called_once()

    def test_race_condition_returns_candidate(self):
        """If key expires between SET and GET, treat as new group."""
        correlator, mock_redis = _make_correlator_with_mock_redis()
        mock_redis.set.return_value = False  # key exists at SET time
        mock_redis.get.return_value = None    # but expired by GET time

        result = asyncio.get_event_loop().run_until_complete(
            correlator.get_or_create(_alert("HighErrorRate"), "incident-003")
        )

        assert result == "incident-003"

    def test_redis_error_returns_candidate(self):
        """When Redis is unavailable, degrade gracefully and treat as new."""
        correlator, mock_redis = _make_correlator_with_mock_redis()
        mock_redis.set.side_effect = ConnectionError("Redis down")

        result = asyncio.get_event_loop().run_until_complete(
            correlator.get_or_create(_alert("HighErrorRate"), "incident-004")
        )

        assert result == "incident-004"

    def test_different_services_are_independent(self):
        """Two alerts with different services create two separate groups."""
        correlator, mock_redis = _make_correlator_with_mock_redis()
        mock_redis.set.return_value = True  # always new

        r1 = asyncio.get_event_loop().run_until_complete(
            correlator.get_or_create(_alert("HighErrorRate", "api"), "inc-001")
        )
        r2 = asyncio.get_event_loop().run_until_complete(
            correlator.get_or_create(_alert("HighErrorRate", "checkout"), "inc-002")
        )

        assert r1 == "inc-001"
        assert r2 == "inc-002"

    def test_different_alertnames_are_independent(self):
        """Two alerts with different names create two separate groups."""
        correlator, mock_redis = _make_correlator_with_mock_redis()
        mock_redis.set.return_value = True

        r1 = asyncio.get_event_loop().run_until_complete(
            correlator.get_or_create(_alert("HighErrorRate", "api"), "inc-001")
        )
        r2 = asyncio.get_event_loop().run_until_complete(
            correlator.get_or_create(_alert("HighLatency", "api"), "inc-002")
        )

        assert r1 == "inc-001"
        assert r2 == "inc-002"


# ─── active_groups ────────────────────────────────────────────────────────────

class TestActiveGroups:
    def test_returns_empty_dict_when_no_groups(self):
        correlator, mock_redis = _make_correlator_with_mock_redis()
        mock_redis.keys.return_value = []

        result = asyncio.get_event_loop().run_until_complete(
            correlator.active_groups()
        )

        assert result == {}

    def test_returns_active_groups(self):
        correlator, mock_redis = _make_correlator_with_mock_redis()
        mock_redis.keys.return_value = ["corr:api:higherrorrate", "corr:api:highlatency"]
        mock_redis.mget.return_value = ["inc-001", "inc-002"]

        result = asyncio.get_event_loop().run_until_complete(
            correlator.active_groups()
        )

        assert result == {
            "corr:api:higherrorrate": "inc-001",
            "corr:api:highlatency": "inc-002",
        }

    def test_filters_out_none_values(self):
        """mget may return None for keys that expired between keys() and mget()."""
        correlator, mock_redis = _make_correlator_with_mock_redis()
        mock_redis.keys.return_value = ["corr:api:higherrorrate", "corr:api:expired"]
        mock_redis.mget.return_value = ["inc-001", None]

        result = asyncio.get_event_loop().run_until_complete(
            correlator.active_groups()
        )

        assert "corr:api:expired" not in result
        assert result["corr:api:higherrorrate"] == "inc-001"


# ─── close ────────────────────────────────────────────────────────────────────

class TestClose:
    def test_close_clears_client(self):
        correlator, mock_redis = _make_correlator_with_mock_redis()
        mock_redis.aclose = AsyncMock()

        asyncio.get_event_loop().run_until_complete(correlator.close())

        assert correlator._client is None

    def test_close_is_idempotent(self):
        """Calling close twice should not raise."""
        correlator = AlertCorrelator(redis_url="redis://mock:6379")
        # No client set — close should be a no-op
        asyncio.get_event_loop().run_until_complete(correlator.close())
        asyncio.get_event_loop().run_until_complete(correlator.close())
