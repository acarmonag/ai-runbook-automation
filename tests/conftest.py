"""
Test fixtures for the AI Runbook Automation test suite.
"""

import os
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from agent.llm.base import LLMResponse, ToolCall

# Ensure we never hit real APIs in tests
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")
os.environ.setdefault("PROMETHEUS_URL", "http://localhost:9999")
os.environ.setdefault("APPROVAL_MODE", "DRY_RUN")
os.environ.setdefault("LLM_BACKEND", "ollama")   # tests use a mocked backend anyway


# ─── Sample Alert Payloads ────────────────────────────────────────────────────

def _make_alert(alertname: str, severity: str = "warning", service: str = "api-service") -> dict:
    return {
        "labels": {
            "alertname": alertname,
            "severity": severity,
            "service": service,
            "environment": "production",
        },
        "annotations": {
            "summary": f"{alertname} detected on {service}",
            "description": f"Detailed description of {alertname} on {service}",
        },
        "startsAt": datetime.now(timezone.utc).isoformat(),
        "fingerprint": str(uuid.uuid4())[:16],
    }


@pytest.fixture
def alert_high_error_rate():
    return _make_alert("HighErrorRate", "critical", "api-service")

@pytest.fixture
def alert_high_latency():
    return _make_alert("HighLatency", "warning", "api-service")

@pytest.fixture
def alert_memory_leak():
    return _make_alert("MemoryLeakDetected", "warning", "worker-service")

@pytest.fixture
def alert_service_down():
    return _make_alert("ServiceDown", "critical", "api-service")

@pytest.fixture
def alert_cpu_spike():
    return _make_alert("HighCPU", "warning", "api-service")

@pytest.fixture
def alert_unknown():
    return _make_alert("SomeUnknownAlert", "warning", "mystery-service")


# ─── Alertmanager Webhook Payloads ────────────────────────────────────────────

@pytest.fixture
def webhook_payload_high_error_rate(alert_high_error_rate):
    return {
        "version": "4",
        "groupKey": "{}:{alertname='HighErrorRate'}",
        "truncatedAlerts": 0,
        "status": "firing",
        "receiver": "agent-webhook",
        "groupLabels": {"alertname": "HighErrorRate"},
        "commonLabels": alert_high_error_rate["labels"],
        "commonAnnotations": alert_high_error_rate["annotations"],
        "externalURL": "http://alertmanager:9093",
        "alerts": [
            {
                **alert_high_error_rate,
                "status": "firing",
                "endsAt": "0001-01-01T00:00:00Z",
                "generatorURL": "http://prometheus:9090/graph",
            }
        ],
    }


# ─── Mock LLM Responses (backend-agnostic) ───────────────────────────────────
#
# Tests mock self.llm.chat() directly — no anthropic/openai SDK needed.

def _final_resolution_text(incident_id: str = "test-001") -> str:
    return f"""
Investigation complete. The error rate has normalized.

```json
{{
    "incident_id": "{incident_id}",
    "summary": "High error rate detected and resolved",
    "root_cause": "Temporary spike in database connection errors, self-resolved",
    "actions_taken": ["get_metrics"],
    "outcome": "RESOLVED",
    "recommendations": ["Monitor database connection pool size"]
}}
```
"""


@pytest.fixture
def mock_llm_simple_resolution():
    """Mock LLM: one get_metrics call, then final report."""
    return [
        LLMResponse(
            stop_reason="tool_use",
            tool_calls=[ToolCall(
                id="t001",
                name="get_metrics",
                input={"query": "rate(http_requests_total{status=~'5..'}[5m])"},
            )],
            text="I'll investigate the high error rate by checking metrics.",
            raw_assistant_message={
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "I'll investigate the high error rate."},
                    {"type": "tool_use", "id": "t001", "name": "get_metrics",
                     "input": {"query": "rate(http_requests_total{status=~'5..'}[5m])"}},
                ],
            },
        ),
        LLMResponse(
            stop_reason="end_turn",
            tool_calls=[],
            text=_final_resolution_text(),
            raw_assistant_message={
                "role": "assistant",
                "content": [{"type": "text", "text": _final_resolution_text()}],
            },
        ),
    ]


@pytest.fixture
def mock_llm_with_restart():
    """Mock LLM: get_metrics → get_recent_logs → restart_service → verify → resolve."""
    final = _final_resolution_text("test-002")
    return [
        LLMResponse(
            stop_reason="tool_use",
            tool_calls=[ToolCall(
                id="t001", name="get_metrics",
                input={"query": "rate(http_requests_total{status=~'5..'}[5m])"},
            )],
            text="Checking error metrics.",
            raw_assistant_message={"role": "assistant", "content": [
                {"type": "text", "text": "Checking error metrics."},
                {"type": "tool_use", "id": "t001", "name": "get_metrics",
                 "input": {"query": "rate(http_requests_total{status=~'5..'}[5m])"}},
            ]},
        ),
        LLMResponse(
            stop_reason="tool_use",
            tool_calls=[ToolCall(
                id="t002", name="get_recent_logs",
                input={"service": "api-service", "lines": 100},
            )],
            text="Errors are high. Checking logs.",
            raw_assistant_message={"role": "assistant", "content": [
                {"type": "text", "text": "Errors are high. Checking logs."},
                {"type": "tool_use", "id": "t002", "name": "get_recent_logs",
                 "input": {"service": "api-service", "lines": 100}},
            ]},
        ),
        LLMResponse(
            stop_reason="tool_use",
            tool_calls=[ToolCall(
                id="t003", name="restart_service",
                input={"service": "api-service"},
            )],
            text="Logs show database pool exhaustion. Restarting service.",
            raw_assistant_message={"role": "assistant", "content": [
                {"type": "text", "text": "Restarting service."},
                {"type": "tool_use", "id": "t003", "name": "restart_service",
                 "input": {"service": "api-service"}},
            ]},
        ),
        LLMResponse(
            stop_reason="tool_use",
            tool_calls=[ToolCall(
                id="t004", name="get_metrics",
                input={"query": "rate(http_requests_total{status=~'5..'}[5m])"},
            )],
            text="Verifying after restart.",
            raw_assistant_message={"role": "assistant", "content": [
                {"type": "text", "text": "Verifying after restart."},
                {"type": "tool_use", "id": "t004", "name": "get_metrics",
                 "input": {"query": "rate(http_requests_total{status=~'5..'}[5m])"}},
            ]},
        ),
        LLMResponse(
            stop_reason="end_turn",
            tool_calls=[],
            text=final,
            raw_assistant_message={"role": "assistant", "content": [
                {"type": "text", "text": final},
            ]},
        ),
    ]


# ─── Mock Prometheus/Docker responses ────────────────────────────────────────

@pytest.fixture
def mock_prometheus_response():
    return {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [
                {"metric": {"job": "api-service", "status": "500"},
                 "value": [1705000000.0, "0.153"]},
            ],
        },
    }

@pytest.fixture
def mock_docker_running():
    return {
        "service": "api-service",
        "container_id": "abc123",
        "status": "running",
        "running": True,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": 3600.0,
        "restart_count": 0,
        "exit_code": 0,
        "image": "api-service:latest",
    }

@pytest.fixture
def mock_docker_stopped():
    return {
        "service": "api-service",
        "container_id": "abc123",
        "status": "exited",
        "running": False,
        "started_at": None,
        "uptime_seconds": None,
        "restart_count": 3,
        "exit_code": 1,
        "image": "api-service:latest",
    }


# ─── Sample Runbook YAML ──────────────────────────────────────────────────────

SAMPLE_RUNBOOK_YAML = """
name: test_runbook
description: Test runbook for unit tests
triggers:
  - TestAlert
  - AnotherTestAlert
actions:
  - "get_metrics: Check error rate"
  - "get_recent_logs: Check service logs"
  - "restart_service: Restart if needed"
escalation_threshold: "Escalate if not resolved in 10 minutes"
metadata:
  severity: P2
  team: test
"""

@pytest.fixture
def sample_runbook_yaml():
    return SAMPLE_RUNBOOK_YAML

@pytest.fixture
def temp_runbooks_dir(tmp_path, sample_runbook_yaml):
    runbooks_dir = tmp_path / "runbooks"
    runbooks_dir.mkdir()
    (runbooks_dir / "test_runbook.yml").write_text(sample_runbook_yaml)
    (runbooks_dir / "another_runbook.yml").write_text("""
name: another_runbook
description: Another test runbook
triggers:
  - CpuHigh
  - MemoryHigh
actions:
  - "run_diagnostic: Check system resources"
  - "scale_service: Scale up if needed"
escalation_threshold: "Escalate if CPU stays high after scaling"
""")
    return runbooks_dir
