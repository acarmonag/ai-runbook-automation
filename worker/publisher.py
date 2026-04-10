"""
Redis pub/sub publisher — worker calls this to push state changes
to all connected API WebSocket clients in real time.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

INCIDENT_CHANNEL = "incident_updates"


async def publish_incident_update(
    redis: Any,
    incident_id: str,
    status: str,
    extra: dict[str, Any] | None = None,
) -> None:
    """Publish an incident state change to the Redis pub/sub channel."""
    payload = json.dumps({
        "incident_id": incident_id,
        "status": status,
        **(extra or {}),
    })
    try:
        await redis.publish(INCIDENT_CHANNEL, payload)
    except Exception as exc:
        logger.warning(f"Failed to publish update for {incident_id}: {exc}")
