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

# Active scenario — set via environment variable, overridable at runtime
_SCENARIO = os.environ.get("MOCK_SCENARIO", "high_error_rate")


def _get_active_scenario() -> str:
    return _SCENARIO


def _set_active_scenario(scenario: str) -> None:
    global _SCENARIO
    _SCENARIO = scenario

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
    "database_connection_pool": {
        PHASE_INCIDENT: {
            "error_rate": 0.12,
            "request_rate": 380.0,
            "p99_latency": 5.8,
            "cpu_usage": 0.42,
            "memory_mb": 560.0,
            "healthy": True,
            "db_connections_used": 100,
            "db_connections_waiting": 47,
        },
        PHASE_REMEDIATING: {
            "error_rate": 0.04,
            "request_rate": 380.0,
            "p99_latency": 1.2,
            "cpu_usage": 0.38,
            "memory_mb": 480.0,
            "healthy": True,
            "db_connections_used": 60,
            "db_connections_waiting": 3,
        },
        PHASE_RECOVERED: {
            "error_rate": 0.001,
            "request_rate": 400.0,
            "p99_latency": 0.18,
            "cpu_usage": 0.30,
            "memory_mb": 440.0,
            "healthy": True,
            "db_connections_used": 25,
            "db_connections_waiting": 0,
        },
    },
    "network_latency": {
        PHASE_INCIDENT: {
            "error_rate": 0.08,
            "request_rate": 320.0,
            "p99_latency": 6.4,
            "cpu_usage": 0.35,
            "memory_mb": 480.0,
            "healthy": True,
        },
        PHASE_REMEDIATING: {
            "error_rate": 0.03,
            "request_rate": 350.0,
            "p99_latency": 2.1,
            "cpu_usage": 0.33,
            "memory_mb": 460.0,
            "healthy": True,
        },
        PHASE_RECOVERED: {
            "error_rate": 0.002,
            "request_rate": 420.0,
            "p99_latency": 0.22,
            "cpu_usage": 0.28,
            "memory_mb": 440.0,
            "healthy": True,
        },
    },
    "circuit_breaker_open": {
        PHASE_INCIDENT: {
            "error_rate": 0.45,
            "request_rate": 180.0,
            "p99_latency": 0.05,  # fail-fast, no latency
            "cpu_usage": 0.20,
            "memory_mb": 400.0,
            "healthy": True,
        },
        PHASE_REMEDIATING: {
            "error_rate": 0.15,
            "request_rate": 280.0,
            "p99_latency": 0.8,
            "cpu_usage": 0.30,
            "memory_mb": 420.0,
            "healthy": True,
        },
        PHASE_RECOVERED: {
            "error_rate": 0.002,
            "request_rate": 440.0,
            "p99_latency": 0.18,
            "cpu_usage": 0.32,
            "memory_mb": 430.0,
            "healthy": True,
        },
    },
    "disk_pressure": {
        PHASE_INCIDENT: {
            "error_rate": 0.05,
            "request_rate": 300.0,
            "p99_latency": 1.8,
            "cpu_usage": 0.50,
            "memory_mb": 520.0,
            "healthy": True,
            "disk_usage_pct": 0.93,
        },
        PHASE_REMEDIATING: {
            "error_rate": 0.02,
            "request_rate": 340.0,
            "p99_latency": 0.9,
            "cpu_usage": 0.42,
            "memory_mb": 500.0,
            "healthy": True,
            "disk_usage_pct": 0.78,
        },
        PHASE_RECOVERED: {
            "error_rate": 0.001,
            "request_rate": 400.0,
            "p99_latency": 0.2,
            "cpu_usage": 0.35,
            "memory_mb": 480.0,
            "healthy": True,
            "disk_usage_pct": 0.61,
        },
    },
    "service_degradation_scale": {
        PHASE_INCIDENT: {
            "error_rate": 0.07,
            "request_rate": 900.0,  # traffic spike
            "p99_latency": 3.8,
            "cpu_usage": 0.88,
            "memory_mb": 720.0,
            "healthy": True,
        },
        PHASE_REMEDIATING: {
            "error_rate": 0.03,
            "request_rate": 900.0,
            "p99_latency": 1.4,
            "cpu_usage": 0.55,
            "memory_mb": 580.0,
            "healthy": True,
        },
        PHASE_RECOVERED: {
            "error_rate": 0.003,
            "request_rate": 900.0,
            "p99_latency": 0.28,
            "cpu_usage": 0.38,
            "memory_mb": 520.0,
            "healthy": True,
        },
    },
    "dependency_failure": {
        PHASE_INCIDENT: {
            "error_rate": 0.98,
            "request_rate": 20.0,  # almost all failing
            "p99_latency": 30.0,   # timeout-dominated
            "cpu_usage": 0.15,
            "memory_mb": 350.0,
            "healthy": False,
        },
        PHASE_REMEDIATING: {
            "error_rate": 0.25,
            "request_rate": 200.0,
            "p99_latency": 1.5,
            "cpu_usage": 0.28,
            "memory_mb": 380.0,
            "healthy": True,
        },
        PHASE_RECOVERED: {
            "error_rate": 0.002,
            "request_rate": 430.0,
            "p99_latency": 0.19,
            "cpu_usage": 0.31,
            "memory_mb": 420.0,
            "healthy": True,
        },
    },
    "high_traffic_load": {
        PHASE_INCIDENT: {
            "error_rate": 0.07,
            "request_rate": 1200.0,  # 4x baseline — traffic spike
            "p99_latency": 4.8,
            "cpu_usage": 0.91,
            "memory_mb": 820.0,
            "healthy": True,
        },
        PHASE_REMEDIATING: {
            "error_rate": 0.02,
            "request_rate": 1200.0,
            "p99_latency": 1.4,
            "cpu_usage": 0.58,
            "memory_mb": 680.0,
            "healthy": True,
        },
        PHASE_RECOVERED: {
            "error_rate": 0.003,
            "request_rate": 1200.0,
            "p99_latency": 0.32,
            "cpu_usage": 0.39,
            "memory_mb": 520.0,
            "healthy": True,
        },
    },
    "cache_exhaustion": {
        PHASE_INCIDENT: {
            "error_rate": 0.04,
            "request_rate": 380.0,
            "p99_latency": 3.2,   # cache misses add latency
            "cpu_usage": 0.55,
            "memory_mb": 1900.0,  # Redis memory near limit
            "healthy": True,
            "cache_hit_rate": 0.18,
        },
        PHASE_REMEDIATING: {
            "error_rate": 0.02,
            "request_rate": 380.0,
            "p99_latency": 1.1,
            "cpu_usage": 0.44,
            "memory_mb": 1200.0,
            "healthy": True,
            "cache_hit_rate": 0.62,
        },
        PHASE_RECOVERED: {
            "error_rate": 0.002,
            "request_rate": 420.0,
            "p99_latency": 0.18,
            "cpu_usage": 0.32,
            "memory_mb": 640.0,
            "healthy": True,
            "cache_hit_rate": 0.94,
        },
    },
    "downstream_dependency": {
        PHASE_INCIDENT: {
            "error_rate": 0.62,
            "request_rate": 80.0,   # most requests failing fast
            "p99_latency": 0.08,    # fail-fast circuit breaker
            "cpu_usage": 0.18,
            "memory_mb": 360.0,
            "healthy": False,
        },
        PHASE_REMEDIATING: {
            "error_rate": 0.20,
            "request_rate": 240.0,
            "p99_latency": 1.2,
            "cpu_usage": 0.30,
            "memory_mb": 390.0,
            "healthy": True,
        },
        PHASE_RECOVERED: {
            "error_rate": 0.002,
            "request_rate": 440.0,
            "p99_latency": 0.21,
            "cpu_usage": 0.33,
            "memory_mb": 430.0,
            "healthy": True,
        },
    },
    "pod_crashloop": {
        PHASE_INCIDENT: {
            "error_rate": 0.35,
            "request_rate": 60.0,   # many requests failing during restarts
            "p99_latency": 5.0,
            "cpu_usage": 0.15,      # low CPU — container is crashing, not running
            "memory_mb": 2040.0,    # near OOM limit
            "healthy": False,
        },
        PHASE_REMEDIATING: {
            "error_rate": 0.10,
            "request_rate": 300.0,
            "p99_latency": 1.8,
            "cpu_usage": 0.40,
            "memory_mb": 780.0,
            "healthy": True,
        },
        PHASE_RECOVERED: {
            "error_rate": 0.002,
            "request_rate": 440.0,
            "p99_latency": 0.22,
            "cpu_usage": 0.35,
            "memory_mb": 480.0,
            "healthy": True,
        },
    },
}


def _get_metrics() -> dict[str, Any]:
    """Return scenario metrics for the current phase, auto-advancing if needed."""
    scenario = _get_active_scenario()
    maybe_auto_advance(scenario)
    phase = get_phase(scenario)
    scenario_phases = SCENARIO_METRICS.get(scenario, SCENARIO_METRICS["high_error_rate"])
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

    if "pg_stat_activity" in query or ("connection" in query.lower() and "pool" in query.lower()):
        used = metrics.get("db_connections_used", 25)
        waiting = metrics.get("db_connections_waiting", 0)
        return _make_instant_result(
            {"datname": "app", "state": "active"},
            float(used + waiting),
        )

    if "disk" in query.lower() or "filesystem" in query.lower():
        disk_pct = metrics.get("disk_usage_pct", 0.45)
        # Return free bytes fraction — agents interpret low free as high usage
        free_bytes = (1.0 - disk_pct) * 100 * 1024 * 1024 * 1024  # 100GB total simulated
        return _make_instant_result(
            {"mountpoint": "/var/log", "device": "/dev/sda1"},
            free_bytes,
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
        scenario = _get_active_scenario()
        phase = get_phase(scenario)
        if scenario == "memory_leak" and phase == PHASE_INCIDENT:
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
    scenario = _get_active_scenario()
    action = body.get("action", "unknown")
    result = trigger_remediation(scenario, action)
    return {
        "scenario": scenario,
        "action": action,
        "new_phase": result["phase"],
        "message": f"Scenario '{scenario}' advanced to phase '{result['phase']}'",
    }


@app.get("/api/v1/alert-status")
async def alert_status():
    """Return whether the current alert is still firing."""
    scenario = _get_active_scenario()
    maybe_auto_advance(scenario)
    phase = get_phase(scenario)
    firing = phase == PHASE_INCIDENT
    return {
        "scenario": scenario,
        "phase": phase,
        "alert_firing": firing,
        "message": "Alert resolved — remediation was successful" if not firing else "Alert is still firing",
    }


@app.post("/api/v1/reset")
async def reset_scenario():
    """Reset scenario state back to INCIDENT (useful for re-running tests)."""
    scenario = _get_active_scenario()
    reset(scenario)
    return {"scenario": scenario, "phase": PHASE_INCIDENT, "message": "Scenario reset to INCIDENT"}


@app.post("/api/v1/scenario")
async def set_scenario(body: dict = Body(default={})):
    """Switch the active scenario at runtime (for demo/testing)."""
    requested = body.get("scenario", "")
    if requested not in SCENARIO_METRICS:
        return {
            "error": f"Unknown scenario '{requested}'. Available: {list(SCENARIO_METRICS)}",
            "status": "error",
        }
    _set_active_scenario(requested)
    reset(requested)
    return {"scenario": requested, "phase": PHASE_INCIDENT, "message": f"Switched to scenario '{requested}'"}


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
