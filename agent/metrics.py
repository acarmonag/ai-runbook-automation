"""
Prometheus metrics for the SRE agent.

Exposed on the API at GET /metrics (text/plain; version=0.0.4).
Updated by the worker after each incident completes.

Metrics:
  sre_agent_incidents_total           counter  {status, alert_name}
  sre_agent_incident_duration_seconds histogram {status}
  sre_agent_actions_total             counter  {action, result}
  sre_agent_llm_tokens_total          counter  {model}
  sre_agent_llm_retries_total         counter  {}
  sre_agent_active_incidents          gauge    {}
  sre_agent_alert_correlations_total  counter  {}
"""

from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    CollectorRegistry,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

# Use a dedicated registry so we don't accidentally expose process/platform
# metrics that aren't relevant to the SRE agent.
REGISTRY = CollectorRegistry()

incidents_total = Counter(
    "sre_agent_incidents_total",
    "Total incidents processed by outcome",
    ["status", "alert_name"],
    registry=REGISTRY,
)

incident_duration_seconds = Histogram(
    "sre_agent_incident_duration_seconds",
    "Time from alert received to incident resolved/escalated",
    ["status"],
    buckets=[30, 60, 120, 300, 600, 1800, 3600],
    registry=REGISTRY,
)

actions_total = Counter(
    "sre_agent_actions_total",
    "Tool/action invocations by name and result",
    ["action", "result"],
    registry=REGISTRY,
)

llm_tokens_total = Counter(
    "sre_agent_llm_tokens_total",
    "LLM tokens consumed (input + output)",
    ["model"],
    registry=REGISTRY,
)

llm_retries_total = Counter(
    "sre_agent_llm_retries_total",
    "Number of LLM call retries due to transient errors",
    registry=REGISTRY,
)

active_incidents = Gauge(
    "sre_agent_active_incidents",
    "Incidents currently being processed",
    registry=REGISTRY,
)

alert_correlations_total = Counter(
    "sre_agent_alert_correlations_total",
    "Alerts merged into existing incidents by the correlation engine",
    registry=REGISTRY,
)


def record_incident(
    status: str,
    alert_name: str,
    duration_seconds: float,
    actions: list[dict],
    tokens_used: int = 0,
    model: str = "unknown",
) -> None:
    """Called by the worker after an incident finishes."""
    incidents_total.labels(status=status, alert_name=alert_name).inc()
    incident_duration_seconds.labels(status=status).observe(duration_seconds)

    for action in actions:
        actions_total.labels(
            action=action.get("action", "unknown"),
            result=action.get("result", "UNKNOWN"),
        ).inc()

    if tokens_used > 0:
        llm_tokens_total.labels(model=model).inc(tokens_used)


def metrics_output() -> tuple[bytes, str]:
    """Return (body_bytes, content_type) for the /metrics endpoint."""
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
