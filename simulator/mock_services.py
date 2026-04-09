"""
Mock Docker services — simulates service lifecycle for testing
without requiring a real Docker environment.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class MockContainer:
    name: str
    status: str = "running"
    restart_count: int = 0
    started_at: float = field(default_factory=time.time)
    replicas: int = 1
    image: str = "mock-image:latest"
    exit_code: int = 0
    logs: list[str] = field(default_factory=list)


# Pre-seeded logs for each scenario
SCENARIO_LOGS: dict[str, list[str]] = {
    "high_error_rate": [
        "2024-01-15T10:00:01Z INFO Starting api-service",
        "2024-01-15T10:00:02Z INFO Listening on :8080",
        "2024-01-15T10:05:12Z ERROR Failed to connect to database: connection timeout",
        "2024-01-15T10:05:13Z ERROR Request failed: /api/users - 500 Internal Server Error",
        "2024-01-15T10:05:14Z ERROR Request failed: /api/orders - 500 Internal Server Error",
        "2024-01-15T10:05:15Z ERROR Database connection pool exhausted",
        "2024-01-15T10:05:16Z CRITICAL Unhandled exception in request handler",
        "2024-01-15T10:05:16Z ERROR Traceback: database.PoolExhaustedError: no connections available",
        "2024-01-15T10:05:17Z ERROR Request failed: /api/users - 500 Internal Server Error",
        "2024-01-15T10:05:18Z ERROR Request failed: /api/products - 500 Internal Server Error",
    ],
    "high_latency": [
        "2024-01-15T10:00:01Z INFO Starting api-service",
        "2024-01-15T10:00:02Z INFO Listening on :8080",
        "2024-01-15T10:10:01Z WARN Request slow: /api/search - 3200ms",
        "2024-01-15T10:10:05Z WARN Request slow: /api/products - 4100ms",
        "2024-01-15T10:10:10Z WARN High CPU usage detected: 87%",
        "2024-01-15T10:10:15Z WARN Request queue depth: 450 (normal: 50)",
        "2024-01-15T10:10:20Z WARN Request slow: /api/users - 5200ms",
    ],
    "memory_leak": [
        "2024-01-15T09:00:01Z INFO Starting worker-service",
        "2024-01-15T09:00:02Z INFO Worker pool initialized: 10 workers",
        "2024-01-15T09:30:15Z WARN Memory usage high: 1024MB",
        "2024-01-15T09:45:30Z WARN Memory usage growing: 1536MB",
        "2024-01-15T10:00:00Z ERROR Memory usage critical: 1843MB / 2048MB limit",
        "2024-01-15T10:00:01Z ERROR GC pressure high — pause time 250ms",
        "2024-01-15T10:00:05Z WARN Object cache not being evicted — possible memory leak in CacheManager",
        "2024-01-15T10:00:10Z ERROR Out of memory warning — approaching container limit",
    ],
    "service_down": [
        "2024-01-15T10:00:01Z INFO Starting api-service",
        "2024-01-15T10:00:02Z INFO Connected to database",
        "2024-01-15T10:02:15Z ERROR Failed to bind to port 8080: address in use",
        "2024-01-15T10:02:15Z FATAL Cannot start HTTP server",
        "2024-01-15T10:02:16Z ERROR Unrecoverable error — shutting down",
    ],
    "cpu_spike": [
        "2024-01-15T10:00:01Z INFO Starting api-service",
        "2024-01-15T10:00:02Z INFO Listening on :8080",
        "2024-01-15T10:15:00Z WARN CPU usage at 91%",
        "2024-01-15T10:15:01Z WARN Request rate spike: 450 req/s (normal: 200 req/s)",
        "2024-01-15T10:15:05Z WARN CPU throttling detected",
        "2024-01-15T10:15:10Z WARN Request timeout: /api/compute - 10000ms",
        "2024-01-15T10:15:15Z WARN CPU usage at 94% — approaching saturation",
    ],
}


class MockDockerClient:
    """
    Mock Docker client for testing without a real Docker daemon.
    Can simulate service operations and state changes.
    """

    def __init__(self, scenario: str = "high_error_rate"):
        self.scenario = scenario
        self._services: dict[str, MockContainer] = {
            "api-service": MockContainer(
                name="api-service",
                status="running" if scenario != "service_down" else "exited",
                restart_count=0 if scenario != "service_down" else 3,
                exit_code=0 if scenario != "service_down" else 1,
            ),
            "worker-service": MockContainer(
                name="worker-service",
                status="running",
                restart_count=0,
            ),
            "cache-service": MockContainer(
                name="cache-service",
                status="running",
                restart_count=0,
            ),
        }
        # Pre-seed logs
        logs = SCENARIO_LOGS.get(scenario, [])
        for name in self._services:
            if name in scenario or scenario in name or True:
                self._services[name].logs = logs

    def get_container(self, name: str) -> Optional[MockContainer]:
        return self._services.get(name)

    def restart_service(self, name: str) -> dict[str, Any]:
        container = self._services.get(name)
        if not container:
            return {"success": False, "error": f"Service {name} not found"}

        container.restart_count += 1
        container.status = "running"
        container.exit_code = 0
        container.started_at = time.time()

        # After restart, clear error state
        container.logs.append(
            f"[RESTART #{container.restart_count}] Service {name} restarted successfully"
        )

        logger.info(f"Mock: Restarted service {name} (restart #{container.restart_count})")
        return {
            "success": True,
            "service": name,
            "restart_count": container.restart_count,
            "new_status": "running",
        }

    def scale_service(self, name: str, replicas: int) -> dict[str, Any]:
        container = self._services.get(name)
        if not container:
            return {"success": False, "error": f"Service {name} not found"}

        old_replicas = container.replicas
        container.replicas = replicas

        logger.info(f"Mock: Scaled {name} from {old_replicas} to {replicas} replicas")
        return {
            "success": True,
            "service": name,
            "previous_replicas": old_replicas,
            "current_replicas": replicas,
        }

    def get_logs(self, name: str, tail: int = 100) -> list[str]:
        container = self._services.get(name)
        if not container:
            return []
        return container.logs[-tail:]

    def get_status(self, name: str) -> dict[str, Any]:
        container = self._services.get(name)
        if not container:
            return {"name": name, "status": "not_found"}

        uptime = time.time() - container.started_at if container.status == "running" else 0
        return {
            "name": name,
            "status": container.status,
            "running": container.status == "running",
            "restart_count": container.restart_count,
            "replicas": container.replicas,
            "uptime_seconds": round(uptime, 1),
            "exit_code": container.exit_code,
            "image": container.image,
        }
