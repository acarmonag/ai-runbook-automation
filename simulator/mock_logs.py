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

_SCENARIO = os.environ.get("MOCK_SCENARIO", "high_error_rate")


def _get_active_scenario() -> str:
    """Return the active scenario — imports from mock_prometheus at runtime to stay in sync."""
    try:
        from simulator.mock_prometheus import _get_active_scenario as _prom_get
        return _prom_get()
    except Exception:
        return _SCENARIO


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
    "database_connection_pool": {
        PHASE_INCIDENT: [
            f"{_ts(180)} INFO  [api] DB pool: used=45, idle=55, waiting=0",
            f"{_ts(150)} WARN  [api] DB pool pressure increasing: used=82, idle=18, waiting=5",
            f"{_ts(120)} ERROR [api] Database connection pool exhausted (pool_size=100, waiting=47)",
            f"{_ts(115)} ERROR [api] Failed to acquire connection after 5000ms timeout",
            f"{_ts(110)} ERROR [api] HikariPool-1 - Connection is not available, request timed out after 5000ms",
            f"{_ts(105)} ERROR [api] com.zaxxer.hikari.pool.HikariPool: Timeout after 30000ms",
            f"{_ts(100)} WARN  [api] Slow query detected: SELECT * FROM user_sessions took 8200ms",
            f"{_ts(95)}  ERROR [api] GET /api/v1/orders 500 — DB unavailable",
            f"{_ts(90)}  ERROR [api] POST /api/v1/checkout 500 — connection pool exhausted",
            f"{_ts(85)}  WARN  [api] Idle connections not being released — possible connection leak",
            f"{_ts(80)}  ERROR [api] Health check: DEGRADED (db_pool_waiting=47)",
            f"{_ts(60)}  ERROR [api] 12% of requests failing due to DB connection timeouts",
        ],
        PHASE_RECOVERED: [
            f"{_ts(60)}  INFO  [api] Service restart initiated — connection pool reset",
            f"{_ts(55)}  INFO  [api] HikariPool-1 - Starting...",
            f"{_ts(50)}  INFO  [api] HikariPool-1 - Start completed (pool_size=100)",
            f"{_ts(45)}  INFO  [api] DB pool: used=22, idle=78, waiting=0",
            f"{_ts(35)}  INFO  [api] GET /api/v1/orders 200 18ms",
            f"{_ts(25)}  INFO  [api] POST /api/v1/checkout 200 22ms",
            f"{_ts(15)}  INFO  [api] Health check: OK (db_pool_utilization=22%)",
            f"{_ts(5)}   INFO  [api] All endpoints healthy",
        ],
    },
    "network_latency": {
        PHASE_INCIDENT: [
            f"{_ts(120)} WARN  [api] p99 latency: 6400ms (SLO threshold: 500ms)",
            f"{_ts(115)} WARN  [api] Slow call to inventory-service: 4800ms (timeout: 5000ms)",
            f"{_ts(110)} WARN  [api] Slow call to payment-service: 5100ms — timeout imminent",
            f"{_ts(105)} ERROR [api] DNS resolution for auth-service took 2200ms",
            f"{_ts(100)} WARN  [api] TCP connection to cache:6379 took 3800ms",
            f"{_ts(95)}  ERROR [api] Read timeout on downstream payment-service after 5000ms",
            f"{_ts(90)}  WARN  [api] Network packet loss detected on eth0: 12%",
            f"{_ts(85)}  ERROR [api] context deadline exceeded calling inventory:8081",
            f"{_ts(80)}  WARN  [api] Retrying request to payment-service (attempt 2/3)",
            f"{_ts(75)}  ERROR [api] All retries exhausted for payment-service — returning 503",
            f"{_ts(60)}  WARN  [api] Health check: DEGRADED (p99=6400ms)",
        ],
        PHASE_RECOVERED: [
            f"{_ts(60)}  INFO  [api] Network path to payment-service restored",
            f"{_ts(50)}  INFO  [api] p99 latency: 220ms (normal)",
            f"{_ts(40)}  INFO  [api] All downstream calls completing within SLO",
            f"{_ts(30)}  INFO  [api] Packet loss on eth0: 0%",
            f"{_ts(20)}  INFO  [api] Health check: OK (p99=220ms)",
            f"{_ts(10)}  INFO  [api] All services healthy",
        ],
    },
    "circuit_breaker_open": {
        PHASE_INCIDENT: [
            f"{_ts(120)} WARN  [api] inventory-service error rate rising: 15%",
            f"{_ts(110)} WARN  [api] inventory-service error rate: 45% — circuit breaker threshold approaching",
            f"{_ts(100)} ERROR [api] Circuit breaker OPEN for inventory-service (threshold=50% exceeded)",
            f"{_ts(98)}  WARN  [api] CircuitBreakerOpenException: inventory-service is OPEN, failing fast",
            f"{_ts(95)}  WARN  [api] Fallback activated for /api/v1/inventory — returning cached data",
            f"{_ts(90)}  ERROR [api] 45% of checkout requests failing — inventory unavailable",
            f"{_ts(85)}  WARN  [api] inventory-service: 0/3 health checks passing",
            f"{_ts(80)}  ERROR [api] Circuit breaker OPEN — all inventory calls rejected",
            f"{_ts(70)}  WARN  [api] Half-open probe attempt failed — inventory still unhealthy",
            f"{_ts(60)}  ERROR [api] Circuit breaker stuck OPEN for 60s",
        ],
        PHASE_RECOVERED: [
            f"{_ts(60)}  INFO  [api] inventory-service restarted",
            f"{_ts(55)}  INFO  [api] Circuit breaker transitioning OPEN → HALF_OPEN",
            f"{_ts(50)}  INFO  [api] Half-open probe succeeded — inventory-service healthy",
            f"{_ts(45)}  INFO  [api] Circuit breaker CLOSED — normal operation resumed",
            f"{_ts(35)}  INFO  [api] inventory-service error rate: 0.1%",
            f"{_ts(20)}  INFO  [api] All checkout flows operational",
            f"{_ts(10)}  INFO  [api] Health check: OK",
        ],
    },
    "disk_pressure": {
        PHASE_INCIDENT: [
            f"{_ts(180)} WARN  [api] Disk usage: 75% (/var/log)",
            f"{_ts(150)} WARN  [api] Disk usage: 83% — log rotation threshold approaching",
            f"{_ts(120)} ERROR [api] Disk usage: 93% on /var/log — CRITICAL",
            f"{_ts(115)} ERROR [api] Failed to write log: No space left on device (ENOSPC)",
            f"{_ts(110)} ERROR [api] IOException: write /tmp/upload_3847.tmp: no space left on device",
            f"{_ts(105)} ERROR [api] Database write failed: disk full (/data: 94% used)",
            f"{_ts(100)} WARN  [api] Log file /var/log/api/access.log: 4.2GB (rotation overdue)",
            f"{_ts(95)}  ERROR [api] POST /api/v1/upload 500 — temp file write failed",
            f"{_ts(90)}  WARN  [api] Core dump found: /var/core/core.23481 (2.1GB)",
            f"{_ts(80)}  ERROR [api] Health check: DEGRADED (disk=/var/log:93%)",
            f"{_ts(60)}  ERROR [api] Multiple write operations failing due to disk full",
        ],
        PHASE_RECOVERED: [
            f"{_ts(60)}  INFO  [api] Service restart — log buffers flushed and rotated",
            f"{_ts(55)}  INFO  [api] Log rotation completed: freed 2.3GB",
            f"{_ts(50)}  INFO  [api] Disk usage: 61% (down from 93%)",
            f"{_ts(40)}  INFO  [api] All write operations succeeding",
            f"{_ts(30)}  INFO  [api] Health check: OK (disk=61%)",
            f"{_ts(10)}  INFO  [api] All services healthy",
        ],
    },
    "service_degradation_scale": {
        PHASE_INCIDENT: [
            f"{_ts(120)} WARN  [api] Traffic spike detected: 900 req/s (baseline: 300 req/s)",
            f"{_ts(115)} WARN  [api] Request queue depth: 2847 (normal: <100)",
            f"{_ts(110)} WARN  [api] p99 latency: 3800ms (SLO: 500ms)",
            f"{_ts(105)} WARN  [api] CPU usage at 88% — all replicas saturated",
            f"{_ts(100)} ERROR [api] Thread pool exhausted: 500/500 threads active",
            f"{_ts(95)}  ERROR [api] Request rejected: queue full (capacity=5000)",
            f"{_ts(90)}  WARN  [api] Autoscaler: HPA target CPU 80% (current: 88%) — scaling up",
            f"{_ts(85)}  WARN  [api] Autoscaler throttled: max replicas=3 already reached",
            f"{_ts(80)}  ERROR [api] 7% of requests returning 503 — overload",
            f"{_ts(70)}  WARN  [api] Health check: DEGRADED (cpu=88%, queue=2847)",
        ],
        PHASE_RECOVERED: [
            f"{_ts(60)}  INFO  [api] Scaling to 5 replicas — new pods starting",
            f"{_ts(50)}  INFO  [api] New replica api-7d9f4-xk2p9 ready",
            f"{_ts(45)}  INFO  [api] New replica api-7d9f4-mn3q8 ready",
            f"{_ts(40)}  INFO  [api] Request queue depth: 12 (normal)",
            f"{_ts(35)}  INFO  [api] CPU usage per replica: 38% (down from 88%)",
            f"{_ts(25)}  INFO  [api] p99 latency: 280ms",
            f"{_ts(15)}  INFO  [api] Error rate: 0.3% and falling",
            f"{_ts(5)}   INFO  [api] Health check: OK — all replicas healthy",
        ],
    },
    "dependency_failure": {
        PHASE_INCIDENT: [
            f"{_ts(120)} ERROR [api] payment-service health check FAILED (0/3)",
            f"{_ts(115)} ERROR [api] Connection refused: payment-service:8082",
            f"{_ts(110)} ERROR [api] ECONNREFUSED connecting to payment-service:8082",
            f"{_ts(105)} ERROR [api] 100% of payment API calls failing",
            f"{_ts(100)} ERROR [api] POST /api/v1/checkout 500 — payment-service unavailable",
            f"{_ts(95)}  ERROR [api] Read timeout after 30000ms: payment-service",
            f"{_ts(90)}  WARN  [api] Circuit breaker OPEN for payment-service",
            f"{_ts(85)}  ERROR [api] Fallback payment processor also unreachable",
            f"{_ts(80)}  ERROR [api] All downstream payment routes exhausted — returning 503",
            f"{_ts(70)}  ERROR [api] Health check: CRITICAL (payment-service=DOWN)",
            f"{_ts(60)}  ERROR [api] 98% of checkout requests failing — dependency down",
        ],
        PHASE_RECOVERED: [
            f"{_ts(60)}  INFO  [api] payment-service restarted",
            f"{_ts(55)}  INFO  [api] payment-service health check PASSING (1/3)",
            f"{_ts(50)}  INFO  [api] payment-service health check PASSING (3/3)",
            f"{_ts(45)}  INFO  [api] Circuit breaker CLOSED for payment-service",
            f"{_ts(40)}  INFO  [api] POST /api/v1/checkout 200 — payment restored",
            f"{_ts(30)}  INFO  [api] payment-service error rate: 0.1%",
            f"{_ts(15)}  INFO  [api] Health check: OK",
            f"{_ts(5)}   INFO  [api] All services operational",
        ],
    },
    "high_traffic_load": {
        PHASE_INCIDENT: [
            f"{_ts(120)} INFO  [api] Traffic spike detected: 1200 req/s (4x baseline)",
            f"{_ts(115)} WARN  [api] CPU throttling: CPU quota exhausted on all 3 replicas",
            f"{_ts(110)} WARN  [api] p99 latency: 4.8s (SLO: 1.0s) — scale out needed",
            f"{_ts(105)} INFO  [api] GET /api/v1/products 200 4200ms",
            f"{_ts(100)} WARN  [api] Request queue backing up: 340 queued requests",
            f"{_ts(95)}  WARN  [api] HPA at max replicas=3, cannot auto-scale further",
            f"{_ts(90)}  INFO  [api] Service is healthy — performance limited by capacity",
            f"{_ts(85)}  INFO  [api] 7% of requests returning 503 (overload rejection)",
            f"{_ts(75)}  INFO  [api] Current replicas: 3/3 — all at 91% CPU",
        ],
        PHASE_RECOVERED: [
            f"{_ts(60)}  INFO  [api] Scaled to 6 replicas — distributing load",
            f"{_ts(50)}  INFO  [api] CPU usage: 38% per replica (was 91%)",
            f"{_ts(40)}  INFO  [api] p99 latency: 0.32s — within SLO",
            f"{_ts(30)}  INFO  [api] Request queue empty",
            f"{_ts(15)}  INFO  [api] Health check: OK — all replicas healthy",
            f"{_ts(5)}   INFO  [api] Traffic handling: 1200 req/s with acceptable latency",
        ],
    },
    "cache_exhaustion": {
        PHASE_INCIDENT: [
            f"{_ts(120)} WARN  [api] Redis memory usage: 1900MB / 2000MB (95%)",
            f"{_ts(115)} WARN  [api] Cache hit rate dropped: 94% → 18%",
            f"{_ts(110)} ERROR [api] Redis eviction triggered: evicted_keys=2000/min",
            f"{_ts(105)} WARN  [api] Cache miss fallback to database — latency spike",
            f"{_ts(100)} INFO  [api] GET /api/v1/catalog 200 3200ms (cache miss, db hit)",
            f"{_ts(95)}  ERROR [api] Redis: OOM, eviction policy: allkeys-lru",
            f"{_ts(90)}  WARN  [api] Database connection pool stress: 72/100 connections used",
            f"{_ts(85)}  INFO  [api] p99 latency: 3.2s — cache layer ineffective",
            f"{_ts(75)}  WARN  [api] Hot keys: user_session_* evicted 500 times",
        ],
        PHASE_RECOVERED: [
            f"{_ts(60)}  INFO  [api] Scaled to 4 replicas — cache load distributed",
            f"{_ts(50)}  INFO  [api] Redis memory: 640MB / 2000MB (32%)",
            f"{_ts(40)}  INFO  [api] Cache hit rate recovering: 62% → 94%",
            f"{_ts(30)}  INFO  [api] p99 latency: 0.18s — cache effective",
            f"{_ts(15)}  INFO  [api] Database connection pool: 22/100 connections",
            f"{_ts(5)}   INFO  [api] Health check: OK",
        ],
    },
    "downstream_dependency": {
        PHASE_INCIDENT: [
            f"{_ts(120)} ERROR [api] inventory-service health check FAILED",
            f"{_ts(115)} ERROR [api] ECONNREFUSED: inventory:8081",
            f"{_ts(110)} WARN  [api] Circuit breaker for inventory-service: OPEN",
            f"{_ts(105)} ERROR [api] GET /api/v1/product/123 500 — inventory unavailable",
            f"{_ts(100)} ERROR [api] 62% of requests failing due to missing inventory data",
            f"{_ts(95)}  WARN  [api] Circuit breaker fail-fast: 0ms response (no connection attempted)",
            f"{_ts(90)}  ERROR [api] inventory-service: no healthy endpoints in pool",
            f"{_ts(80)}  INFO  [api] Local service is healthy — problem is external dependency",
            f"{_ts(70)}  ERROR [api] GET /api/v1/catalog 500 — inventory-service ECONNREFUSED",
        ],
        PHASE_RECOVERED: [
            f"{_ts(60)}  INFO  [api] inventory-service reachable again",
            f"{_ts(50)}  INFO  [api] Circuit breaker HALF-OPEN: testing 1 request",
            f"{_ts(45)}  INFO  [api] Circuit breaker CLOSED: inventory-service healthy",
            f"{_ts(35)}  INFO  [api] GET /api/v1/product/123 200 45ms",
            f"{_ts(20)}  INFO  [api] Error rate: 0.2%",
            f"{_ts(5)}   INFO  [api] All services operational",
        ],
    },
    "pod_crashloop": {
        PHASE_INCIDENT: [
            f"{_ts(120)} ERROR [api] OOMKilled: container memory usage 2040MB exceeded limit 2048MB",
            f"{_ts(115)} INFO  [api] Container restarting (restart #7 in 10 minutes)",
            f"{_ts(110)} WARN  [api] Memory growing: 80MB/min — possible memory leak",
            f"{_ts(105)} ERROR [api] OOMKilled — same restart pattern as last 6 kills",
            f"{_ts(100)} ERROR [api] Heap dump: large number of HttpSession objects not being released",
            f"{_ts(95)}  WARN  [api] JVM heap: 1.9GB / 2.0GB (95% utilized)",
            f"{_ts(90)}  INFO  [api] Requests failing during restart window (35% error rate)",
            f"{_ts(80)}  WARN  [api] CrashLoopBackOff — next restart in 5 minutes",
            f"{_ts(70)}  ERROR [api] Session cache leak: 50,000 unclosed sessions",
        ],
        PHASE_RECOVERED: [
            f"{_ts(60)}  INFO  [api] Scaled to 3 replicas — maintaining availability",
            f"{_ts(50)}  INFO  [api] api-pod-new: started successfully",
            f"{_ts(45)}  INFO  [api] Restarted with -XX:MaxHeapSize=1g flag applied",
            f"{_ts(35)}  INFO  [api] Memory usage stable: 480MB (was 2040MB at kill)",
            f"{_ts(20)}  INFO  [api] No OOM events in last 20 minutes",
            f"{_ts(10)}  INFO  [api] Health check: OK — all pods stable",
            f"{_ts(5)}   INFO  [api] Restart count stable at 7 (no new restarts)",
        ],
    },
}


@router.get("/api/v1/logs")
async def get_mock_logs(service: str = "api", lines: int = 100):
    """Return synthetic log lines for the active scenario."""
    scenario = _get_active_scenario()
    phase = get_phase(scenario)
    # Use RECOVERED logs if recovered, else INCIDENT logs
    display_phase = PHASE_RECOVERED if phase == PHASE_RECOVERED else PHASE_INCIDENT
    scenario_logs = SCENARIO_LOGS.get(scenario, SCENARIO_LOGS["high_error_rate"])
    logs = scenario_logs.get(display_phase, [])
    return {
        "service": service,
        "scenario": scenario,
        "phase": phase,
        "line_count": len(logs),
        "logs": logs[-min(lines, len(logs)):],
    }
