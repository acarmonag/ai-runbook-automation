"""
Synthetic log generator — returns realistic log lines for each scenario.

Exposed via GET /api/v1/logs on mock-prometheus so the agent worker
can retrieve logs even when Docker containers aren't accessible.
"""

import os
import time
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter

from simulator.scenario_state import get_phase, PHASE_INCIDENT, PHASE_RECOVERED

router = APIRouter()

SCENARIO = os.environ.get("MOCK_SCENARIO", "high_error_rate")


def _ts(offset_seconds: int = 0) -> str:
    """ISO timestamp offset from now."""
    dt = datetime.now(timezone.utc) - timedelta(seconds=abs(offset_seconds))
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


SCENARIO_LOGS: dict[str, dict[str, list[str]]] = {
    "high_error_rate": {
        PHASE_INCIDENT: [
            f"{_ts(120)} INFO  [api] Starting request handler",
            f"{_ts(115)} INFO  [api] GET /api/v1/users 200 12ms",
            f"{_ts(110)} ERROR [api] NullPointerException in UserService.getUser()",
            f"{_ts(110)} ERROR [api] java.lang.NullPointerException: user object is null",
            f"{_ts(108)} ERROR [api] at UserService.java:142",
            f"{_ts(105)} INFO  [api] GET /api/v1/orders 500 3ms",
            f"{_ts(100)} ERROR [api] Database connection pool exhausted (pool_size=10, waiting=47)",
            f"{_ts(98)}  ERROR [api] Failed to acquire connection after 5000ms timeout",
            f"{_ts(95)}  INFO  [api] POST /api/v1/checkout 500 5ms",
            f"{_ts(90)}  ERROR [api] CRITICAL: error rate 15.3% exceeds threshold 5%",
            f"{_ts(85)}  ERROR [api] HTTP 500: Internal Server Error on /api/v1/cart",
            f"{_ts(80)}  ERROR [api] HTTP 500: Internal Server Error on /api/v1/users",
            f"{_ts(75)}  WARN  [api] Circuit breaker OPEN for downstream service 'inventory'",
            f"{_ts(70)}  ERROR [api] Connection refused: inventory:8081",
            f"{_ts(60)}  ERROR [api] Traceback (most recent call last):",
            f"{_ts(59)}  ERROR [api]   File 'api/handlers.py', line 88, in handle_request",
            f"{_ts(58)}  ERROR [api] KeyError: 'user_id' in session context",
            f"{_ts(55)}  ERROR [api] HTTP 500 on /api/v1/profile (repeated 23x in last 60s)",
            f"{_ts(50)}  INFO  [api] Health check: DEGRADED (error_rate=0.153)",
            f"{_ts(30)}  ERROR [api] Unhandled exception: connection pool timeout",
        ],
        PHASE_RECOVERED: [
            f"{_ts(60)}  INFO  [api] Service restart initiated",
            f"{_ts(55)}  INFO  [api] Database connection pool reset (pool_size=10)",
            f"{_ts(50)}  INFO  [api] Service started successfully",
            f"{_ts(45)}  INFO  [api] GET /api/v1/users 200 8ms",
            f"{_ts(40)}  INFO  [api] POST /api/v1/checkout 200 12ms",
            f"{_ts(35)}  INFO  [api] GET /api/v1/orders 200 9ms",
            f"{_ts(30)}  INFO  [api] All endpoints healthy",
            f"{_ts(20)}  INFO  [api] Health check: OK (error_rate=0.002)",
            f"{_ts(10)}  INFO  [api] GET /api/v1/users 200 7ms",
            f"{_ts(5)}   INFO  [api] POST /api/v1/cart 200 10ms",
        ],
    },
    "high_latency": {
        PHASE_INCIDENT: [
            f"{_ts(120)} INFO  [api] Request queue depth: 847 (normal: <50)",
            f"{_ts(115)} WARN  [api] Slow query detected: SELECT * FROM orders took 3200ms",
            f"{_ts(110)} WARN  [api] p99 latency 4.2s exceeds SLO threshold of 1s",
            f"{_ts(105)} WARN  [api] CPU throttling detected: usage at 94%",
            f"{_ts(100)} WARN  [api] GET /api/v1/orders 200 4100ms (timeout imminent)",
            f"{_ts(95)}  WARN  [api] Thread pool saturation: 200/200 threads active",
            f"{_ts(90)}  WARN  [api] GC pause: 2.3s stop-the-world collection",
            f"{_ts(85)}  WARN  [api] Slow query: UPDATE user_sessions took 2800ms",
            f"{_ts(80)}  WARN  [api] External API call to payment-service: 3900ms",
            f"{_ts(75)}  ERROR [api] Request timeout after 5000ms on /api/v1/checkout",
            f"{_ts(70)}  WARN  [api] Connection pool at 95% capacity",
            f"{_ts(60)}  WARN  [api] Health check: SLOW (p99=4200ms)",
            f"{_ts(30)}  WARN  [api] Latency spike continues — recommend service restart",
        ],
        PHASE_RECOVERED: [
            f"{_ts(60)}  INFO  [api] Service restarted — JVM heap reset",
            f"{_ts(50)}  INFO  [api] p99 latency: 280ms (down from 4200ms)",
            f"{_ts(40)}  INFO  [api] CPU usage: 38% (down from 94%)",
            f"{_ts(30)}  INFO  [api] Thread pool: 12/200 active",
            f"{_ts(20)}  INFO  [api] Health check: OK (p99=250ms)",
            f"{_ts(10)}  INFO  [api] All endpoints responding normally",
        ],
    },
    "memory_leak": {
        PHASE_INCIDENT: [
            f"{_ts(300)} INFO  [api] Memory usage: 512MB",
            f"{_ts(240)} INFO  [api] Memory usage: 768MB",
            f"{_ts(180)} WARN  [api] Memory usage: 1024MB — growth detected",
            f"{_ts(120)} WARN  [api] Memory usage: 1400MB — leak suspected",
            f"{_ts(90)}  WARN  [api] Memory usage: 1600MB — GC pressure high",
            f"{_ts(60)}  ERROR [api] Memory usage: 1843MB — approaching limit (2048MB)",
            f"{_ts(55)}  ERROR [api] OutOfMemoryError imminent — heap at 90%",
            f"{_ts(50)}  WARN  [api] Full GC triggered — pause 1.8s",
            f"{_ts(45)}  ERROR [api] Cache eviction failures — leaked references",
            f"{_ts(40)}  ERROR [api] com.example.cache.LeakingCache: 47238 entries not released",
            f"{_ts(35)}  WARN  [api] Heap dump recommended",
            f"{_ts(30)}  ERROR [api] OOM risk: memory growing 50MB/min",
            f"{_ts(20)}  WARN  [api] Health check: DEGRADED (memory=1843MB, limit=2048MB)",
        ],
        PHASE_RECOVERED: [
            f"{_ts(60)}  INFO  [api] Service restart complete — memory reset",
            f"{_ts(55)}  INFO  [api] Memory usage: 380MB (fresh JVM heap)",
            f"{_ts(40)}  INFO  [api] Cache initialized (0 leaked entries)",
            f"{_ts(30)}  INFO  [api] Health check: OK (memory=380MB)",
            f"{_ts(15)}  INFO  [api] Memory stable at 395MB",
            f"{_ts(5)}   INFO  [api] All services healthy",
        ],
    },
    "service_down": {
        PHASE_INCIDENT: [
            f"{_ts(120)} ERROR [api] Segmentation fault (core dumped)",
            f"{_ts(119)} ERROR [api] Process exited with code 139",
            f"{_ts(118)} ERROR [api] Supervisor: respawn attempt 1/3",
            f"{_ts(115)} ERROR [api] Supervisor: respawn attempt 2/3",
            f"{_ts(112)} ERROR [api] Supervisor: respawn attempt 3/3 — giving up",
            f"{_ts(110)} ERROR [api] Service is DOWN — all health checks failing",
            f"{_ts(105)} ERROR [api] 100% of requests returning 503 Service Unavailable",
            f"{_ts(100)} ERROR [api] TCP connection refused on port 8080",
            f"{_ts(90)}  ERROR [api] Upstream api:8080 is unreachable",
            f"{_ts(80)}  ERROR [api] Health check failed 3/3 times",
        ],
        PHASE_RECOVERED: [
            f"{_ts(60)}  INFO  [api] Container restart initiated",
            f"{_ts(50)}  INFO  [api] Service starting on port 8080",
            f"{_ts(45)}  INFO  [api] Database connection established",
            f"{_ts(40)}  INFO  [api] Service ready — accepting requests",
            f"{_ts(35)}  INFO  [api] Health check: OK",
            f"{_ts(20)}  INFO  [api] Request rate normalizing: 420 req/s",
            f"{_ts(10)}  INFO  [api] Error rate: 0.2% (recovering)",
            f"{_ts(5)}   INFO  [api] All systems operational",
        ],
    },
    "cpu_spike": {
        PHASE_INCIDENT: [
            f"{_ts(120)} WARN  [api] CPU usage spike: 94% (normal: ~35%)",
            f"{_ts(115)} WARN  [api] Runaway goroutine detected: worker pool leak",
            f"{_ts(110)} WARN  [api] goroutine count: 48291 (normal: <500)",
            f"{_ts(105)} ERROR [api] CPU throttled by cgroup limit",
            f"{_ts(100)} WARN  [api] Request processing slowed — CPU starved",
            f"{_ts(95)}  WARN  [api] Background job 'cache_rehydration' using 60% CPU",
            f"{_ts(90)}  ERROR [api] Infinite loop detected in EventProcessor.process()",
            f"{_ts(85)}  WARN  [api] p99 latency degraded to 2500ms due to CPU contention",
            f"{_ts(80)}  WARN  [api] Health check: DEGRADED (cpu=94%)",
            f"{_ts(60)}  ERROR [api] CPU usage sustained at 94% for 60s",
        ],
        PHASE_RECOVERED: [
            f"{_ts(60)}  INFO  [api] Service restart — goroutine leak cleared",
            f"{_ts(55)}  INFO  [api] goroutine count: 42 (normal)",
            f"{_ts(45)}  INFO  [api] CPU usage: 38% (down from 94%)",
            f"{_ts(35)}  INFO  [api] Request processing normalized",
            f"{_ts(20)}  INFO  [api] Health check: OK (cpu=38%)",
            f"{_ts(10)}  INFO  [api] All services healthy",
        ],
    },
}


@router.get("/api/v1/logs")
async def get_mock_logs(service: str = "api", lines: int = 100):
    """Return synthetic log lines for the active scenario."""
    phase = get_phase(SCENARIO)
    # Use RECOVERED logs if recovered, else INCIDENT logs
    display_phase = PHASE_RECOVERED if phase == PHASE_RECOVERED else PHASE_INCIDENT
    scenario_logs = SCENARIO_LOGS.get(SCENARIO, SCENARIO_LOGS["high_error_rate"])
    logs = scenario_logs.get(display_phase, [])
    return {
        "service": service,
        "scenario": SCENARIO,
        "phase": phase,
        "line_count": len(logs),
        "logs": logs[-min(lines, len(logs)):],
    }
