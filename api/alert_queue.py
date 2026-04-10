"""
Alert queue — enqueues alerts as ARQ jobs in Redis.

Replaces the old asyncio in-memory queue. Jobs are durable: if the
worker crashes mid-execution, ARQ retries the job on restart.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from arq.connections import ArqRedis, create_pool, RedisSettings

logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")

# Deduplication: fingerprint → incident_id (in-memory, best-effort)
_seen_fingerprints: dict[str, str] = {}


class AlertQueue:
    """Thin wrapper around an ARQ Redis pool."""

    def __init__(self) -> None:
        self._pool: ArqRedis | None = None

    async def start(self) -> None:
        self._pool = await create_pool(RedisSettings.from_dsn(REDIS_URL))
        logger.info("Alert queue connected to Redis")

    async def stop(self) -> None:
        if self._pool:
            await self._pool.aclose()

    async def enqueue(self, alert: dict[str, Any]) -> str | None:
        """
        Enqueue an alert for agent processing.
        Returns the incident_id, or None if the alert is a duplicate.
        """
        fingerprint = alert.get("fingerprint", "")

        if fingerprint and fingerprint in _seen_fingerprints:
            logger.debug(f"Duplicate alert fingerprint {fingerprint}, skipping")
            return None

        incident_id = str(uuid.uuid4())[:8]

        if fingerprint:
            _seen_fingerprints[fingerprint] = incident_id

        if self._pool is None:
            raise RuntimeError("AlertQueue not started — call await start() first")

        await self._pool.enqueue_job("process_alert", incident_id, alert)
        logger.info(
            f"Enqueued alert {alert.get('labels', {}).get('alertname')} as incident {incident_id}"
        )
        return incident_id
