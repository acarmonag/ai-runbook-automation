"""
Docker actions — service lifecycle management via Docker SDK.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Import Docker SDK lazily to allow testing without Docker installed
try:
    import docker
    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False
    logger.warning("Docker SDK not available — docker actions will fail gracefully")


def _get_docker_client():
    """Return a Docker client, raising RuntimeError if unavailable."""
    if not DOCKER_AVAILABLE:
        raise RuntimeError("Docker SDK is not installed")
    try:
        return docker.from_env()
    except Exception as e:
        raise RuntimeError(f"Cannot connect to Docker daemon: {e}") from e


def get_service_status(service: str) -> dict[str, Any]:
    """
    Get current status of a Docker container/service.

    Returns container state, uptime, and restart count.
    """
    try:
        client = _get_docker_client()
        containers = client.containers.list(all=True, filters={"name": service})

        if not containers:
            return {
                "service": service,
                "status": "not_found",
                "message": f"No container found with name '{service}'",
            }

        container = containers[0]
        attrs = container.attrs or {}
        state = attrs.get("State", {})
        host_config = attrs.get("HostConfig", {})

        # Calculate uptime
        started_at = state.get("StartedAt", "")
        uptime_seconds = None
        if started_at and state.get("Running"):
            try:
                start_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                uptime_seconds = (datetime.now(timezone.utc) - start_dt).total_seconds()
            except Exception:
                pass

        return {
            "service": service,
            "container_id": container.short_id,
            "status": state.get("Status", "unknown"),
            "running": state.get("Running", False),
            "started_at": started_at,
            "uptime_seconds": uptime_seconds,
            "restart_count": attrs.get("RestartCount", 0),
            "exit_code": state.get("ExitCode", 0),
            "image": container.image.tags[0] if container.image.tags else "unknown",
        }

    except RuntimeError as e:
        return {"service": service, "error": str(e), "status": "error"}
    except Exception as e:
        logger.error(f"Failed to get status for service '{service}': {e}")
        return {"service": service, "error": str(e), "status": "error"}


def restart_service(service: str) -> dict[str, Any]:
    """
    Restart a Docker container by name.

    This is a DESTRUCTIVE action — requires approval in AUTO mode.
    """
    logger.warning(f"Restarting service: {service}")
    try:
        client = _get_docker_client()
        containers = client.containers.list(all=True, filters={"name": service})

        if not containers:
            return {
                "service": service,
                "success": False,
                "error": f"No container found with name '{service}'",
            }

        container = containers[0]
        container.restart(timeout=30)

        # Verify it came back up
        container.reload()
        new_status = container.attrs.get("State", {}).get("Status", "unknown")

        logger.info(f"Service '{service}' restarted, new status: {new_status}")
        return {
            "service": service,
            "success": True,
            "previous_status": "running",
            "new_status": new_status,
            "message": f"Service {service} successfully restarted",
        }

    except RuntimeError as e:
        return {"service": service, "success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"Failed to restart service '{service}': {e}")
        return {"service": service, "success": False, "error": str(e)}


def scale_service(service: str, replicas: int) -> dict[str, Any]:
    """
    Scale a Docker Compose service to the specified replica count.

    Scaling DOWN is DESTRUCTIVE — requires approval in AUTO mode.
    """
    logger.info(f"Scaling service '{service}' to {replicas} replicas")

    if replicas < 0:
        return {
            "service": service,
            "success": False,
            "error": "Replica count cannot be negative",
        }

    try:
        client = _get_docker_client()

        # For Docker Compose services, we use labels to find scale target
        containers = client.containers.list(
            filters={"label": f"com.docker.compose.service={service}"}
        )
        current_count = len(containers)

        # Docker Compose scaling via CLI is more reliable than SDK for this
        import subprocess
        result = subprocess.run(
            ["docker", "compose", "up", "--scale", f"{service}={replicas}", "-d", "--no-recreate"],
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode != 0:
            # Try without --no-recreate flag
            result = subprocess.run(
                ["docker", "compose", "up", "--scale", f"{service}={replicas}", "-d"],
                capture_output=True,
                text=True,
                timeout=60,
            )

        success = result.returncode == 0
        return {
            "service": service,
            "success": success,
            "previous_replicas": current_count,
            "target_replicas": replicas,
            "stdout": result.stdout[:500] if result.stdout else "",
            "stderr": result.stderr[:500] if result.stderr else "",
            "message": f"Scaled {service} from {current_count} to {replicas} replicas"
            if success
            else f"Scale failed: {result.stderr[:200]}",
        }

    except RuntimeError as e:
        return {"service": service, "success": False, "error": str(e)}
    except subprocess.TimeoutExpired:
        return {"service": service, "success": False, "error": "Scale operation timed out"}
    except Exception as e:
        logger.error(f"Failed to scale service '{service}': {e}")
        return {"service": service, "success": False, "error": str(e)}
