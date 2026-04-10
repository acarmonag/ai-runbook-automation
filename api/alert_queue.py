"""
Alert queue — enqueues alerts as ARQ jobs in Redis.

Replaces the old asyncio in-memory queue. Jobs are durable: if the
worker crashes mid-execution, ARQ retries the job on restart.

Correlation deduplication (via AlertCorrelator) prevents alert storms
from spawning multiple agent runs for the same root cause.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from arq.connections import ArqRedis, create_pool, RedisSettings

from api.correlation import AlertCorrelator

logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")


class AlertQueue:
    """Thin wrapper around an ARQ Redis pool + correlation engine."""

    def __init__(self) -> None:
        self._pool: ArqRedis | None = None
        self._correlator: AlertCorrelator = AlertCorrelator(REDIS_URL)

    async def start(self) -> None:
        self._pool = await create_pool(RedisSettings.from_dsn(REDIS_URL))
        logger.info("Alert queue connected to Redis")

    async def stop(self) -> None:
        if self._pool:
            await self._pool.aclose()
        await self._correlator.close()

    async def enqueue(self, alert: dict[str, Any]) -> tuple[str, bool] | None:
        """
        Enqueue an alert for agent processing.

        Returns:
            (incident_id, is_new) — incident_id is the incident handling this
                alert; is_new is True when a fresh job was queued, False when
                the alert was correlated with an existing incident.
            None — internal error (pool not started).
        """
        if self._pool is None:
            raise RuntimeError("AlertQueue not started — call await start() first")

        candidate_id = str(uuid.uuid4())[:8]

        # Correlation check: merge into existing group if within time window.
        incident_id = await self._correlator.get_or_create(alert, candidate_id)

        if incident_id != candidate_id:
            # Merged into an existing incident — no new job needed.
            logger.info(
                "Alert %s correlated with existing incident %s",
                alert.get("labels", {}).get("alertname"),
                incident_id,
            )
            return incident_id, False

        # New incident — enqueue ARQ job.
        await self._pool.enqueue_job("process_alert", incident_id, alert)
        logger.info(
            "Enqueued alert %s as incident %s",
            alert.get("labels", {}).get("alertname"),
            incident_id,
        )
        return incident_id, True
