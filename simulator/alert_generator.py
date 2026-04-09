"""
Alert generator — generates realistic Alertmanager webhook payloads
for each simulation scenario.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _make_alert(
    alertname: str,
    severity: str,
    service: str,
    summary: str,
    description: str,
    extra_labels: Optional[Dict[str, Any]] = None,
    extra_annotations: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    labels = {
        "alertname": alertname,
        "severity": severity,
        "service": service,
        "environment": "production",
        "team": "platform",
        **(extra_labels or {}),
    }
    annotations = {
        "summary": summary,
        "description": description,
        "runbook_url": f"https://wiki.internal/runbooks/{alertname}",
        **(extra_annotations or {}),
    }
    return {
        "status": "firing",
        "labels": labels,
        "annotations": annotations,
        "startsAt": _now(),
        "endsAt": "0001-01-01T00:00:00Z",
        "generatorURL": f"http://prometheus:9090/graph?g0.expr=alert_{alertname}",
        "fingerprint": str(uuid.uuid4())[:16],
    }


SCENARIOS: Dict[str, Dict[str, Any]] = {
    "high_error_rate": {
        "alert": _make_alert(
            alertname="HighErrorRate",
            severity="critical",
            service="api-service",
            summary="HTTP error rate above 15% for api-service",
            description=(
                "The api-service is returning 5xx errors at 15.3% rate over the last 5 minutes. "
                "This is above the critical threshold of 10%. "
                "Affected endpoints: /api/users, /api/orders"
            ),
            extra_labels={"job": "api-service", "instance": "api-service:8080"},
            extra_annotations={"value": "15.3%", "threshold": "10%"},
        ),
        "description": "Service returning 15% HTTP 500 errors",
    },
    "high_latency": {
        "alert": _make_alert(
            alertname="HighLatency",
            severity="warning",
            service="api-service",
            summary="p99 response latency exceeds 3 seconds for api-service",
            description=(
                "The api-service p99 response latency has been above 3s for 10 minutes. "
                "Current p99: 4.2s, p95: 2.8s, p50: 0.8s. "
                "CPU utilization is at 87% suggesting resource saturation."
            ),
            extra_labels={"quantile": "0.99", "job": "api-service"},
            extra_annotations={"value": "4.2s", "threshold": "3s"},
        ),
        "description": "API p99 latency at 4.2s, CPU at 87%",
    },
    "memory_leak": {
        "alert": _make_alert(
            alertname="MemoryLeakDetected",
            severity="warning",
            service="worker-service",
            summary="worker-service memory usage growing linearly — possible memory leak",
            description=(
                "worker-service memory usage has grown from 256MB to 1.8GB over the past hour "
                "and continues to grow at ~25MB/minute. "
                "Memory limit is 2GB. OOM kill expected within ~8 minutes."
            ),
            extra_labels={"container": "worker-service", "namespace": "production"},
            extra_annotations={"current_mb": "1843", "growth_rate": "25MB/min"},
        ),
        "description": "Worker service memory growing to 1.8GB, approaching OOM",
    },
    "service_down": {
        "alert": _make_alert(
            alertname="ServiceDown",
            severity="critical",
            service="api-service",
            summary="api-service is completely unreachable",
            description=(
                "api-service health check has been failing for 3 consecutive checks (90 seconds). "
                "All instances are returning connection refused. "
                "Last successful health check: 3 minutes ago."
            ),
            extra_labels={"job": "api-service", "instance": "api-service:8080"},
            extra_annotations={"duration": "3m", "last_seen": "3m ago"},
        ),
        "description": "Service completely down, health checks failing for 90s",
    },
    "cpu_spike": {
        "alert": _make_alert(
            alertname="HighCPU",
            severity="warning",
            service="api-service",
            summary="api-service CPU usage at 94% — possible CPU saturation",
            description=(
                "api-service CPU usage has been above 90% for 15 minutes. "
                "CPU throttling is occurring. Request queue is backing up. "
                "Current load: 450 req/s, normal: 200 req/s"
            ),
            extra_labels={"container": "api-service", "cpu": "94"},
            extra_annotations={"value": "94%", "threshold": "90%", "duration": "15m"},
        ),
        "description": "CPU at 94% with request queue backing up",
    },
}


def generate_alert(scenario: str) -> Dict[str, Any]:
    """Generate an Alertmanager webhook payload for a scenario."""
    if scenario not in SCENARIOS:
        raise ValueError(
            f"Unknown scenario: '{scenario}'. Available: {list(SCENARIOS)}"
        )

    scenario_data = SCENARIOS[scenario]
    alert = scenario_data["alert"]

    # Refresh timestamp
    alert = dict(alert)
    alert["startsAt"] = _now()
    alert["fingerprint"] = str(uuid.uuid4())[:16]

    return {
        "version": "4",
        "groupKey": "{}:{{alertname=\"{}\"}}".format("{}", alert['labels']['alertname']),
        "truncatedAlerts": 0,
        "status": "firing",
        "receiver": "agent-webhook",
        "groupLabels": {"alertname": alert["labels"]["alertname"]},
        "commonLabels": alert["labels"],
        "commonAnnotations": alert["annotations"],
        "externalURL": "http://alertmanager:9093",
        "alerts": [alert],
    }


def list_scenarios() -> List[str]:
    return list(SCENARIOS)
