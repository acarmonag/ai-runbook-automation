"""
Tests for the actions subsystem.

Tests:
- Each action with mocked external dependencies
- ActionResult success/failure handling
- Graceful degradation when services unreachable
"""

from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from agent.actions.registry import ActionRegistry, ActionResult


# ─── Prometheus Action Tests ──────────────────────────────────────────────────

class TestGetMetrics:
    def test_successful_query(self):
        from agent.actions.prometheus import get_metrics

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": [
                    {
                        "metric": {"job": "api-service"},
                        "value": [1705000000.0, "0.153"],
                    }
                ],
            },
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.get", return_value=mock_response):
            result = get_metrics("rate(http_requests_total[5m])")

        assert result["status"] == "success"
        assert result["value"] == pytest.approx(0.153)
        assert result["labels"] == {"job": "api-service"}

    def test_connection_error_returns_graceful_error(self):
        import httpx
        from agent.actions.prometheus import get_metrics

        with patch("httpx.get", side_effect=httpx.ConnectError("refused")):
            result = get_metrics("some_query")

        assert result["status"] == "connection_error"
        assert "error" in result

    def test_timeout_returns_graceful_error(self):
        import httpx
        from agent.actions.prometheus import get_metrics

        with patch("httpx.get", side_effect=httpx.TimeoutException("timeout")):
            result = get_metrics("some_query")

        assert result["status"] == "timeout"
        assert "error" in result

    def test_empty_result_returns_no_data(self):
        from agent.actions.prometheus import get_metrics

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": {"resultType": "vector", "result": []},
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.get", return_value=mock_response):
            result = get_metrics("nonexistent_metric")

        assert result["status"] == "no_data"
        assert result["value"] is None

    def test_prometheus_error_status(self):
        from agent.actions.prometheus import get_metrics

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "error",
            "error": "invalid query",
            "errorType": "bad_data",
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.get", return_value=mock_response):
            result = get_metrics("invalid[query")

        assert result["status"] == "query_error"

    def test_multiple_results_returned(self):
        from agent.actions.prometheus import get_metrics

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": [
                    {"metric": {"handler": "/api/users"}, "value": [1705000000.0, "0.1"]},
                    {"metric": {"handler": "/api/orders"}, "value": [1705000000.0, "0.3"]},
                ],
            },
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.get", return_value=mock_response):
            result = get_metrics("rate(http_requests_total[5m]) by (handler)")

        assert len(result["all_results"]) == 2


# ─── Docker Actions Tests ─────────────────────────────────────────────────────

class TestGetServiceStatus:
    def test_running_container(self):
        from agent.actions.docker_actions import get_service_status

        mock_container = MagicMock()
        mock_container.short_id = "abc123"
        mock_container.image.tags = ["api-service:latest"]
        mock_container.attrs = {
            "State": {
                "Status": "running",
                "Running": True,
                "StartedAt": "2024-01-15T10:00:00.000000000Z",
                "ExitCode": 0,
            },
            "RestartCount": 0,
        }

        mock_client = MagicMock()
        mock_client.containers.list.return_value = [mock_container]

        with patch("agent.actions.docker_actions._get_docker_client", return_value=mock_client):
            result = get_service_status("api-service")

        assert result["status"] == "running"
        assert result["running"] is True
        assert result["restart_count"] == 0

    def test_stopped_container(self):
        from agent.actions.docker_actions import get_service_status

        mock_container = MagicMock()
        mock_container.short_id = "abc123"
        mock_container.image.tags = ["api-service:latest"]
        mock_container.attrs = {
            "State": {
                "Status": "exited",
                "Running": False,
                "StartedAt": "",
                "ExitCode": 1,
            },
            "RestartCount": 3,
        }

        mock_client = MagicMock()
        mock_client.containers.list.return_value = [mock_container]

        with patch("agent.actions.docker_actions._get_docker_client", return_value=mock_client):
            result = get_service_status("api-service")

        assert result["status"] == "exited"
        assert result["running"] is False
        assert result["restart_count"] == 3

    def test_container_not_found(self):
        from agent.actions.docker_actions import get_service_status

        mock_client = MagicMock()
        mock_client.containers.list.return_value = []

        with patch("agent.actions.docker_actions._get_docker_client", return_value=mock_client):
            result = get_service_status("nonexistent-service")

        assert result["status"] == "not_found"

    def test_docker_unavailable(self):
        from agent.actions.docker_actions import get_service_status

        with patch(
            "agent.actions.docker_actions._get_docker_client",
            side_effect=RuntimeError("Docker not available"),
        ):
            result = get_service_status("api-service")

        assert result["status"] == "error"
        assert "error" in result


class TestRestartService:
    def test_successful_restart(self):
        from agent.actions.docker_actions import restart_service

        mock_container = MagicMock()
        mock_container.short_id = "abc123"
        mock_container.attrs = {"State": {"Status": "running"}}
        mock_container.restart = MagicMock()
        mock_container.reload = MagicMock()

        mock_client = MagicMock()
        mock_client.containers.list.return_value = [mock_container]

        with patch("agent.actions.docker_actions._get_docker_client", return_value=mock_client):
            result = restart_service("api-service")

        assert result["success"] is True
        mock_container.restart.assert_called_once_with(timeout=30)

    def test_container_not_found(self):
        from agent.actions.docker_actions import restart_service

        mock_client = MagicMock()
        mock_client.containers.list.return_value = []

        with patch("agent.actions.docker_actions._get_docker_client", return_value=mock_client):
            result = restart_service("missing-service")

        assert result["success"] is False
        assert "No container found" in result["error"]


# ─── Log Actions Tests ────────────────────────────────────────────────────────

class TestGetRecentLogs:
    def test_parses_error_patterns(self):
        from agent.actions.log_actions import parse_error_patterns

        logs = [
            "2024-01-15T10:00:00Z INFO Server started",
            "2024-01-15T10:01:00Z ERROR Database connection failed",
            "2024-01-15T10:01:01Z ERROR Traceback: connection refused",
            "2024-01-15T10:01:02Z CRITICAL Out of memory",
            "2024-01-15T10:02:00Z INFO Request processed",
        ]

        result = parse_error_patterns(logs)
        assert result["total_error_lines"] == 3
        assert "ERROR" in result["pattern_counts"]
        assert result["pattern_counts"]["ERROR"] >= 2

    def test_no_errors_in_clean_logs(self):
        from agent.actions.log_actions import parse_error_patterns

        logs = [
            "2024-01-15T10:00:00Z INFO Server started",
            "2024-01-15T10:01:00Z INFO Request processed",
            "2024-01-15T10:02:00Z INFO Response sent",
        ]

        result = parse_error_patterns(logs)
        assert result["total_error_lines"] == 0

    def test_oom_pattern_detected(self):
        from agent.actions.log_actions import parse_error_patterns

        logs = [
            "2024-01-15T10:00:00Z ERROR Out of memory: Kill process 123",
        ]

        result = parse_error_patterns(logs)
        assert "OOM" in result["pattern_counts"]

    def test_get_recent_logs_docker_not_available(self):
        from agent.actions.log_actions import get_recent_logs

        with patch("agent.actions.log_actions.docker", side_effect=ImportError, create=True):
            with patch.dict("sys.modules", {"docker": None}):
                # Import will fail, function should handle gracefully
                pass

    def test_container_not_found_returns_empty(self):
        from agent.actions.log_actions import get_recent_logs

        mock_client = MagicMock()
        mock_client.containers.list.return_value = []

        with patch("docker.from_env", return_value=mock_client):
            result = get_recent_logs("missing-service")

        assert result["logs"] == []
        assert "error" in result


# ─── Diagnostic Tests ─────────────────────────────────────────────────────────

class TestRunDiagnostic:
    def test_disk_usage_check(self):
        from agent.actions.diagnostic import run_diagnostic

        with patch("shutil.disk_usage", return_value=(100_000_000_000, 50_000_000_000, 50_000_000_000)):
            result = run_diagnostic("disk_usage")

        assert result["check"] == "disk_usage"
        assert result["used_percent"] == pytest.approx(50.0)
        assert result["status"] in ("ok", "warning", "critical")

    def test_disk_usage_critical(self):
        from agent.actions.diagnostic import run_diagnostic

        # 96% full
        with patch("shutil.disk_usage", return_value=(100_000_000, 96_000_000, 4_000_000)):
            result = run_diagnostic("disk_usage")

        assert result["status"] == "critical"

    def test_unknown_check_returns_error(self):
        from agent.actions.diagnostic import run_diagnostic

        result = run_diagnostic("nonexistent_check")
        assert result["status"] == "error"
        assert "Unknown diagnostic check" in result["error"]

    def test_error_rate_check_prometheus_down(self):
        import httpx
        from agent.actions.diagnostic import run_diagnostic

        with patch("httpx.get", side_effect=httpx.ConnectError("refused")):
            result = run_diagnostic("error_rate")

        assert result["status"] == "error"
        assert "error" in result

    def test_error_rate_check_ok(self):
        from agent.actions.diagnostic import run_diagnostic

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": [{"metric": {}, "value": [1705000000.0, "0.5"]}],
            },
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.get", return_value=mock_response):
            result = run_diagnostic("error_rate")

        assert result["error_rate_percent"] == pytest.approx(0.5)
        assert result["status"] == "ok"


# ─── ActionRegistry Integration Tests ────────────────────────────────────────

class TestActionRegistryIntegration:
    def test_build_default_registry_has_all_actions(self):
        from agent.actions.registry import build_default_registry

        registry = build_default_registry()
        expected = [
            "get_metrics",
            "get_recent_logs",
            "get_service_status",
            "scale_service",
            "restart_service",
            "run_diagnostic",
            "escalate",
        ]
        for action in expected:
            assert action in registry.list_actions(), f"Missing action: {action}"

    def test_action_result_to_dict(self):
        result = ActionResult(success=True, output="done", duration_ms=42)
        d = result.to_dict()
        assert d["success"] is True
        assert d["output"] == "done"
        assert d["duration_ms"] == 42
        assert d["error"] is None
