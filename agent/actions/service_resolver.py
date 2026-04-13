from __future__ import annotations

"""
Service name resolver — maps logical service names to actual Docker container names.

Alert labels often use short names (e.g. "api", "checkout") while Docker Compose
creates containers with project-prefixed names (e.g. "agent-api-1", "agent-checkout-1").

Resolution order:
  1. Exact match
  2. Prefix variants: "{project}-{service}-1", "{project}-{service}"
  3. Suffix variants: "{service}-1"
  4. Partial match (container name contains the service name)
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

def resolve_container_name(service: str, client=None) -> Optional[str]:
    """
    Resolve a logical service name to a running Docker container name.

    Returns the first matching container name, or None if not found.
    Requires a docker client — if not provided, creates one.
    """
    try:
        if client is None:
            import docker
            client = docker.from_env()
    except Exception as e:
        logger.warning(f"Cannot create Docker client for name resolution: {e}")
        return None

    candidates = _build_candidates(service)

    for candidate in candidates:
        try:
            containers = client.containers.list(all=True, filters={"name": candidate})
            if containers:
                found = containers[0].name
                if found != service:
                    logger.info(f"Resolved service '{service}' → container '{found}'")
                return found
        except Exception as e:
            logger.debug(f"Candidate '{candidate}' lookup failed: {e}")
            continue

    logger.warning(f"Could not resolve service '{service}' to any container. Tried: {candidates}")
    return None


def _build_candidates(service: str) -> list[str]:
    """Generate candidate container names for a logical service name."""
    project = os.environ.get("COMPOSE_PROJECT_NAME", "agent")
    return [
        service,                              # exact
        f"{project}-{service}-1",             # compose default: project-service-1
        f"{project}-{service}",               # without replica suffix
        f"{service}-1",                       # without project prefix
        f"{project}_{service}_1",             # older compose format
        f"{project}_{service}",
    ]


def resolve_or_original(service: str, client=None) -> str:
    """
    Resolve service name, falling back to the original name if resolution fails.
    Safe to call even when Docker is unavailable.
    """
    try:
        resolved = resolve_container_name(service, client)
        return resolved if resolved else service
    except Exception:
        return service
