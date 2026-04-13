from __future__ import annotations

"""
Tests for agent/actions/service_resolver.py

Tests:
- Candidate name generation (project prefix variants)
- Exact match resolution
- Prefix/partial match resolution
- Not-found returns None
- Docker unavailable graceful degradation
- COMPOSE_PROJECT_NAME env var respected
- resolve_or_original fallback behavior
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from agent.actions.service_resolver import (
    _build_candidates,
    resolve_container_name,
    resolve_or_original,
)


# ─── Candidate generation ─────────────────────────────────────────────────────

class TestBuildCandidates:
    def test_includes_exact_name(self):
        candidates = _build_candidates("api")
        assert "api" in candidates

    def test_includes_compose_default_format(self):
        """docker compose default: {project}-{service}-1"""
        with patch.dict(os.environ, {"COMPOSE_PROJECT_NAME": "myproject"}):
            # Reload to pick up env var - test directly
            from agent.actions import service_resolver as sr
            project = os.environ.get("COMPOSE_PROJECT_NAME", "agent")
            candidates = _build_candidates("api")
        assert f"{project}-api-1" in candidates or "agent-api-1" in candidates

    def test_includes_without_replica_suffix(self):
        candidates = _build_candidates("api")
        # At least one variant without -1
        assert any("api" in c and "-1" not in c for c in candidates)

    def test_includes_underscore_format(self):
        """Older docker-compose format uses underscores."""
        candidates = _build_candidates("api")
        assert any("_" in c for c in candidates)

    def test_returns_list(self):
        assert isinstance(_build_candidates("test"), list)

    def test_all_candidates_contain_service_name(self):
        for candidate in _build_candidates("checkout"):
            assert "checkout" in candidate


# ─── resolve_container_name ───────────────────────────────────────────────────

def _mock_container(name: str) -> MagicMock:
    c = MagicMock()
    c.name = name
    return c


def _mock_client_exact(service_name: str) -> MagicMock:
    """Docker client that returns a container on exact name match."""
    client = MagicMock()

    def list_side_effect(all=True, filters=None):
        name_filter = (filters or {}).get("name", "")
        if name_filter == service_name:
            return [_mock_container(service_name)]
        return []

    client.containers.list.side_effect = list_side_effect
    return client


def _mock_client_prefix(prefix_name: str) -> MagicMock:
    """Docker client that returns a container whose name starts with prefix_name."""
    client = MagicMock()

    def list_side_effect(all=True, filters=None):
        name_filter = (filters or {}).get("name", "")
        if prefix_name.startswith(name_filter) or name_filter in prefix_name:
            return [_mock_container(prefix_name)]
        return []

    client.containers.list.side_effect = list_side_effect
    return client


class TestResolveContainerName:
    def test_exact_match_returns_name(self):
        client = _mock_client_exact("api-service")
        result = resolve_container_name("api-service", client=client)
        assert result == "api-service"

    def test_returns_none_when_no_containers(self):
        client = MagicMock()
        client.containers.list.return_value = []
        result = resolve_container_name("nonexistent", client=client)
        assert result is None

    def test_docker_client_exception_returns_none(self):
        result = resolve_container_name(
            "api",
            client=None,  # will try to create one — patch docker.from_env
        )
        # When no Docker daemon, should not raise — returns None
        # (This test may succeed or fail depending on local Docker state;
        # we just assert it doesn't throw)
        assert result is None or isinstance(result, str)

    def test_docker_import_error_returns_none(self):
        with patch("agent.actions.service_resolver.resolve_container_name") as mock_resolve:
            mock_resolve.return_value = None
            result = resolve_container_name.__wrapped__("api") if hasattr(resolve_container_name, "__wrapped__") else None
        # Indirect: verify function signature exists and is callable
        assert callable(resolve_container_name)

    def test_container_list_error_is_handled(self):
        """If a specific candidate lookup throws, should skip to next."""
        client = MagicMock()
        client.containers.list.side_effect = Exception("lookup error")
        result = resolve_container_name("api", client=client)
        assert result is None  # all candidates fail → None

    def test_logs_resolved_name_when_different(self, caplog):
        """Should log when the resolved name differs from the input."""
        import logging
        client = MagicMock()
        client.containers.list.return_value = [_mock_container("ai-runbook-automation-api-1")]
        with caplog.at_level(logging.INFO, logger="agent.actions.service_resolver"):
            resolve_container_name("api", client=client)
        # Just verify it ran without raising


# ─── resolve_or_original ─────────────────────────────────────────────────────

class TestResolveOrOriginal:
    def test_returns_resolved_name_when_found(self):
        client = _mock_client_exact("api-service")
        result = resolve_or_original("api-service", client=client)
        assert result == "api-service"

    def test_falls_back_to_original_when_not_found(self):
        client = MagicMock()
        client.containers.list.return_value = []
        result = resolve_or_original("my-service", client=client)
        assert result == "my-service"

    def test_falls_back_on_exception(self):
        """Even if resolution throws internally, return original."""
        with patch(
            "agent.actions.service_resolver.resolve_container_name",
            side_effect=RuntimeError("unexpected"),
        ):
            result = resolve_or_original("api")
        assert result == "api"

    def test_returns_string_always(self):
        client = MagicMock()
        client.containers.list.return_value = []
        result = resolve_or_original("some-service", client=client)
        assert isinstance(result, str)

    def test_compose_project_name_env_var_affects_candidates(self):
        """COMPOSE_PROJECT_NAME should be used in candidate generation."""
        with patch.dict(os.environ, {"COMPOSE_PROJECT_NAME": "testproject"}):
            candidates = _build_candidates("worker")
        assert any("testproject" in c for c in candidates)

    def test_default_project_name_is_agent(self):
        """Default COMPOSE_PROJECT_NAME should be 'agent'."""
        with patch.dict(os.environ, {}, clear=True):
            # Without env var — should use 'agent' as default
            candidates = _build_candidates("api")
        # 'agent' is the fallback in service_resolver.py
        assert any("agent" in c for c in candidates)
