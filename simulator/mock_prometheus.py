"""
Mock Prometheus server — serves realistic PromQL-like responses
for each simulation scenario.
"""

import os
import time
from typing import Any

from fastapi import FastAPI, Query

app = FastAPI(title="Mock Prometheus", description="Simulated Prometheus for testing")

# Active scenario — set via environment variable
SCENARIO = os.environ.get("MOCK_SCENARIO", "high_error_rate")

# Metric data by scenario
SCENARIO_METRICS: dict[str, dict[str, Any]] = {
    "high_error_rate": {
        "error_rate": 0.153,
        "request_rate": 450.0,
        "p99_latency": 0.8,
        "cpu_usage": 0.45,
        "memory_mb": 512.0,
        "healthy": True,
    },
    "high_latency": {
        "error_rate": 0.01,
        "request_rate": 450.0,
        "p99_latency": 4.2,
        "cpu_usage": 0.87,
        "memory_mb": 768.0,
        "healthy": True,
    },
    "memory_leak": {
        "error_rate": 0.02,
        "request_rate": 200.0,
        "p99_latency": 1.2,
        "cpu_usage": 0.55,
        "memory_mb": 1843.0,
        "healthy": True,
    },
    "service_down": {
        "error_rate": 1.0,
        "request_rate": 0.0,
        "p99_latency": 30.0,
        "cpu_usage": 0.0,
        "memory_mb": 0.0,
        "healthy": False,
    },
    "cpu_spike": {
        "error_rate": 0.03,
        "request_rate": 450.0,
        "p99_latency": 2.5,
        "cpu_usage": 0.94,
        "memory_mb": 600.0,
        "healthy": True,
    },
}


def _make_instant_result(metric: dict, value: float) -> dict:
    """Build a Prometheus instant query result."""
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


@app.get("/api/v1/query")
async def instant_query(query: str = Query(..., description="PromQL query")):
    """
    Handle instant queries — maps common PromQL patterns to scenario-based values.
    """
    metrics = SCENARIO_METRICS.get(SCENARIO, SCENARIO_METRICS["high_error_rate"])
    ts = time.time()

    # Error rate queries
    if "5.." in query or "error" in query.lower():
        rate = metrics["error_rate"]
        return _make_instant_result(
            {"job": "api-service", "service": "api-service", "status": "500"},
            rate,
        )

    # Latency / histogram queries
    if "histogram_quantile" in query or "duration" in query or "latency" in query:
        return _make_instant_result(
            {"job": "api-service", "handler": "/api/v1", "quantile": "0.99"},
            metrics["p99_latency"],
        )

    # CPU queries
    if "cpu" in query.lower():
        return _make_instant_result(
            {"container_name": "api-service", "pod": "api-service-0"},
            metrics["cpu_usage"],
        )

    # Memory queries
    if "memory" in query.lower():
        memory_bytes = metrics["memory_mb"] * 1024 * 1024
        return _make_instant_result(
            {"container_name": "api-service", "pod": "api-service-0"},
            memory_bytes,
        )

    # Request rate
    if "http_requests_total" in query or "request" in query.lower():
        return _make_instant_result(
            {"job": "api-service", "handler": "/api/v1", "method": "GET"},
            metrics["request_rate"],
        )

    # Up/health check
    if query.strip() == "up" or "up{" in query:
        value = 1.0 if metrics["healthy"] else 0.0
        return _make_instant_result(
            {"job": "api-service", "instance": "api-service:8080"},
            value,
        )

    # Generic "1" health check
    if query.strip() == "1":
        return _make_instant_result({"__name__": "scalar"}, 1.0)

    # Default — return empty
    return _make_no_data()


@app.get("/api/v1/query_range")
async def range_query(
    query: str = Query(...),
    start: float = Query(default=None),
    end: float = Query(default=None),
    step: str = Query(default="60"),
):
    """Handle range queries — returns simulated time series."""
    metrics = SCENARIO_METRICS.get(SCENARIO, SCENARIO_METRICS["high_error_rate"])
    now = time.time()
    start = start or (now - 3600)
    end = end or now
    step_seconds = int(step.rstrip("s")) if step.endswith("s") else int(step)

    timestamps = list(range(int(start), int(end), step_seconds))

    if "memory" in query.lower():
        # Simulate growing memory for memory_leak scenario
        base = metrics["memory_mb"] * 1024 * 1024
        if SCENARIO == "memory_leak":
            values = [
                [ts, str(base - (len(timestamps) - i) * 25 * 1024 * 1024)]
                for i, ts in enumerate(timestamps)
            ]
        else:
            values = [[ts, str(base)] for ts in timestamps]
    else:
        base = 0.45
        values = [[ts, str(base)] for ts in timestamps]

    return {
        "status": "success",
        "data": {
            "resultType": "matrix",
            "result": [
                {
                    "metric": {"job": "api-service"},
                    "values": values,
                }
            ],
        },
    }


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
