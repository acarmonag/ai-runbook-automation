"""
Mock Prometheus server — serves realistic PromQL-like responses
for each simulation scenario, with stateful phase tracking.

Phases: INCIDENT → REMEDIATING → RECOVERED
Remediation is triggered via POST /api/v1/remediation
"""

import os
import time
from typing import Any

from fastapi import FastAPI, Query, Body

from simulator.mock_logs import router as logs_router
from simulator.scenario_state import (
    get_phase, trigger_remediation, maybe_auto_advance, reset,
    PHASE_INCIDENT, PHASE_REMEDIATING, PHASE_RECOVERED,
)

app = FastAPI(title="Mock Prometheus", description="Simulated Prometheus for testing")
app.include_router(logs_router)

# Active scenario — set via environment variable
SCENARIO = os.environ.get("MOCK_SCENARIO", "high_error_rate")

# ── Metric definitions per scenario ──────────────────────────────────────────
# Each scenario has INCIDENT and RECOVERED metric sets.
# REMEDIATING = lerp between the two (we just show recovering values).

SCENARIO_METRICS: dict[str, dict[str, dict[str, Any]]] = {
    "high_error_rate": {
        PHASE_INCIDENT: {
            "error_rate": 0.153,
            "request_rate": 450.0,
            "p99_latency": 0.8,
            "cpu_usage": 0.45,
            "memory_mb": 512.0,
            "healthy": True,
        },
        PHASE_REMEDIATING: {
            "error_rate": 0.06,
            "request_rate": 450.0,
            "p99_latency": 0.5,
            "cpu_usage": 0.38,
            "memory_mb": 480.0,
            "healthy": True,
        },
        PHASE_RECOVERED: {
            "error_rate": 0.002,
            "request_rate": 450.0,
            "p99_latency": 0.15,
            "cpu_usage": 0.30,
            "memory_mb": 420.0,
            "healthy": True,
        },
    },
    "high_latency": {
        PHASE_INCIDENT: {
            "error_rate": 0.01,
            "request_rate": 450.0,
            "p99_latency": 4.2,
            "cpu_usage": 0.87,
            "memory_mb": 768.0,
            "healthy": True,
        },
        PHASE_REMEDIATING: {
            "error_rate": 0.01,
            "request_rate": 450.0,
            "p99_latency": 2.0,
            "cpu_usage": 0.65,
            "memory_mb": 650.0,
            "healthy": True,
        },
        PHASE_RECOVERED: {
            "error_rate": 0.005,
            "request_rate": 450.0,
            "p99_latency": 0.3,
            "cpu_usage": 0.40,
            "memory_mb": 512.0,
            "healthy": True,
        },
    },
    "memory_leak": {
        PHASE_INCIDENT: {
            "error_rate": 0.02,
            "request_rate": 200.0,
            "p99_latency": 1.2,
            "cpu_usage": 0.55,
            "memory_mb": 1843.0,
            "healthy": True,
        },
        PHASE_REMEDIATING: {
            "error_rate": 0.01,
            "request_rate": 250.0,
            "p99_latency": 0.8,
            "cpu_usage": 0.45,
            "memory_mb": 900.0,
            "healthy": True,
        },
        PHASE_RECOVERED: {
            "error_rate": 0.002,
            "request_rate": 300.0,
            "p99_latency": 0.25,
            "cpu_usage": 0.35,
            "memory_mb": 380.0,
            "healthy": True,
        },
    },
    "service_down": {
        PHASE_INCIDENT: {
            "error_rate": 1.0,
            "request_rate": 0.0,
            "p99_latency": 30.0,
            "cpu_usage": 0.0,
            "memory_mb": 0.0,
            "healthy": False,
        },
        PHASE_REMEDIATING: {
            "error_rate": 0.3,
            "request_rate": 150.0,
            "p99_latency": 1.5,
            "cpu_usage": 0.25,
            "memory_mb": 256.0,
            "healthy": True,
        },
        PHASE_RECOVERED: {
            "error_rate": 0.002,
            "request_rate": 420.0,
            "p99_latency": 0.2,
            "cpu_usage": 0.32,
            "memory_mb": 480.0,
            "healthy": True,
        },
    },
    "cpu_spike": {
        PHASE_INCIDENT: {
            "error_rate": 0.03,
            "request_rate": 450.0,
            "p99_latency": 2.5,
            "cpu_usage": 0.94,
            "memory_mb": 600.0,
            "healthy": True,
        },
        PHASE_REMEDIATING: {
            "error_rate": 0.02,
            "request_rate": 450.0,
            "p99_latency": 1.2,
            "cpu_usage": 0.72,
            "memory_mb": 580.0,
            "healthy": True,
        },
        PHASE_RECOVERED: {
            "error_rate": 0.003,
            "request_rate": 450.0,
            "p99_latency": 0.3,
            "cpu_usage": 0.38,
            "memory_mb": 520.0,
            "healthy": True,
        },
    },
}


def _get_metrics() -> dict[str, Any]:
    """Return scenario metrics for the current phase, auto-advancing if needed."""
    maybe_auto_advance(SCENARIO)
    phase = get_phase(SCENARIO)
    scenario_phases = SCENARIO_METRICS.get(SCENARIO, SCENARIO_METRICS["high_error_rate"])
    return scenario_phases.get(phase, scenario_phases[PHASE_INCIDENT])


def _make_instant_result(metric: dict, value: float) -> dict:
    return {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [
                {
                    "metric": metric,
                    "value": [time.time(), str(round(value, 6))],
                }
            ],
        },
    }


def _make_no_data() -> dict:
    return {"status": "success", "data": {"resultType": "vector", "result": []}}


# ── Query endpoints ───────────────────────────────────────────────────────────

@app.get("/api/v1/query")
async def instant_query(query: str = Query(..., description="PromQL query")):
    metrics = _get_metrics()

    if "5.." in query or "error" in query.lower():
        rate = metrics["error_rate"]
        return _make_instant_result(
            {"job": "api-service", "service": "api-service", "status": "500"},
            rate,
        )

    if "histogram_quantile" in query or "duration" in query or "latency" in query:
        return _make_instant_result(
            {"job": "api-service", "handler": "/api/v1", "quantile": "0.99"},
            metrics["p99_latency"],
        )

    if "cpu" in query.lower():
        return _make_instant_result(
            {"container_name": "api-service", "pod": "api-service-0"},
            metrics["cpu_usage"],
        )

    if "memory" in query.lower():
        memory_bytes = metrics["memory_mb"] * 1024 * 1024
        return _make_instant_result(
            {"container_name": "api-service", "pod": "api-service-0"},
            memory_bytes,
        )

    if "http_requests_total" in query or "request" in query.lower():
        return _make_instant_result(
            {"job": "api-service", "handler": "/api/v1", "method": "GET"},
            metrics["request_rate"],
        )

    if query.strip() == "up" or "up{" in query:
        value = 1.0 if metrics["healthy"] else 0.0
        return _make_instant_result(
            {"job": "api-service", "instance": "api-service:8080"},
            value,
        )

    if query.strip() == "1":
        return _make_instant_result({"__name__": "scalar"}, 1.0)

    return _make_no_data()


@app.get("/api/v1/query_range")
async def range_query(
    query: str = Query(...),
    start: float = Query(default=None),
    end: float = Query(default=None),
    step: str = Query(default="60"),
):
    metrics = _get_metrics()
    now = time.time()
    start = start or (now - 3600)
    end = end or now
    step_seconds = int(step.rstrip("s")) if step.endswith("s") else int(step)
    timestamps = list(range(int(start), int(end), step_seconds))

    if "memory" in query.lower():
        base = metrics["memory_mb"] * 1024 * 1024
        phase = get_phase(SCENARIO)
        if SCENARIO == "memory_leak" and phase == PHASE_INCIDENT:
            values = [
                [ts, str(base - (len(timestamps) - i) * 25 * 1024 * 1024)]
                for i, ts in enumerate(timestamps)
            ]
        else:
            values = [[ts, str(base)] for ts in timestamps]
    else:
        base = metrics.get("cpu_usage", 0.45)
        values = [[ts, str(base)] for ts in timestamps]

    return {
        "status": "success",
        "data": {
            "resultType": "matrix",
            "result": [{"metric": {"job": "api-service"}, "values": values}],
        },
    }


# ── Remediation notification ──────────────────────────────────────────────────

@app.post("/api/v1/remediation")
async def notify_remediation(body: dict = Body(default={})):
    """
    Called by the agent after performing a remediation action (restart, scale, etc.).
    Advances the scenario phase so subsequent metric queries return improved values.
    """
    action = body.get("action", "unknown")
    result = trigger_remediation(SCENARIO, action)
    return {
        "scenario": SCENARIO,
        "action": action,
        "new_phase": result["phase"],
        "message": f"Scenario '{SCENARIO}' advanced to phase '{result['phase']}'",
    }


@app.get("/api/v1/alert-status")
async def alert_status():
    """Return whether the current alert is still firing."""
    maybe_auto_advance(SCENARIO)
    phase = get_phase(SCENARIO)
    firing = phase == PHASE_INCIDENT
    return {
        "scenario": SCENARIO,
        "phase": phase,
        "alert_firing": firing,
        "message": "Alert resolved — remediation was successful" if not firing else "Alert is still firing",
    }


@app.post("/api/v1/reset")
async def reset_scenario():
    """Reset scenario state back to INCIDENT (useful for re-running tests)."""
    reset(SCENARIO)
    return {"scenario": SCENARIO, "phase": PHASE_INCIDENT, "message": "Scenario reset to INCIDENT"}


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/-/healthy")
async def healthy():
    return {"status": "Prometheus is Healthy."}


@app.get("/-/ready")
async def ready():
    return {"status": "Prometheus is Ready."}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "9091"))
    uvicorn.run(app, host="0.0.0.0", port=port)
