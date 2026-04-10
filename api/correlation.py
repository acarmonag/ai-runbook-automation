"""
Alert correlation engine.

Groups related alerts into a single incident to prevent alert storms from
spawning redundant agent runs. Two alerts are considered correlated when they
share the same (service, alertname) pair and arrive within CORRELATION_WINDOW_SECONDS.

State is stored in Redis so it survives API restarts and works correctly when
multiple API replicas are running behind a load-balancer.

Key format:  corr:{service}:{alertname}
Value:        incident_id
TTL:          CORRELATION_WINDOW_SECONDS  (default 5 min)
"""

from __future__ import annotations

import logging
import os
from typing import Any

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

CORRELATION_WINDOW_SECONDS: int = int(
    os.environ.get("CORRELATION_WINDOW_SECONDS", "300")
)
_CORR_PREFIX = "corr"


class AlertCorrelator:
    """
    Determines whether an incoming alert should be attached to an existing
    incident or trigger a brand-new one.

    Usage::

        corr = AlertCorrelator(redis_url)
        incident_id = await corr.get_or_create(alert_dict, new_incident_id)
        is_new = (incident_id == new_incident_id)
    """

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._client: aioredis.Redis | None = None

    async def _get_client(self) -> aioredis.Redis:
        if self._client is None:
            self._client = aioredis.from_url(
                self._redis_url, decode_responses=True
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    @staticmethod
    def _group_key(alert: dict[str, Any]) -> str:
        labels = alert.get("labels", {})
        service = labels.get("service") or labels.get("job") or "unknown"
        alertname = labels.get("alertname", "unknown")
        # Normalise to lowercase so casing differences don't split groups.
        return f"{_CORR_PREFIX}:{service.lower()}:{alertname.lower()}"

    async def get_or_create(
        self, alert: dict[str, Any], candidate_id: str
    ) -> str:
        """
        Return the incident_id that should handle this alert.

        * If an active group exists for (service, alertname) → return its id.
        * Otherwise → register candidate_id as the new group leader and return it.

        The TTL is refreshed every time a correlated alert arrives so a sustained
        alert storm keeps accumulating into one incident rather than splitting at
        the window boundary.
        """
        key = self._group_key(alert)
        client = await self._get_client()

        try:
            # SET key candidate_id EX ttl NX  — only sets if not already present
            was_set: bool = await client.set(
                key, candidate_id, ex=CORRELATION_WINDOW_SECONDS, nx=True
            )
            if was_set:
                # New group — this alert is the leader.
                logger.info(
                    "Correlation: new group %s → incident %s", key, candidate_id
                )
                return candidate_id

            # Group exists — get the leader incident_id and refresh TTL.
            existing_id: str | None = await client.get(key)
            if existing_id:
                await client.expire(key, CORRELATION_WINDOW_SECONDS)
                logger.info(
                    "Correlation: alert merged into existing incident %s (group %s)",
                    existing_id,
                    key,
                )
                return existing_id

            # Race condition: key expired between SET and GET — treat as new.
            await client.set(key, candidate_id, ex=CORRELATION_WINDOW_SECONDS)
            return candidate_id

        except Exception as exc:
            # Redis unavailable — degrade gracefully, treat every alert as new.
            logger.warning("Correlation Redis error (%s) — skipping dedup", exc)
            return candidate_id

    async def active_groups(self) -> dict[str, str]:
        """Return all active correlation groups {key: incident_id} (for observability)."""
        client = await self._get_client()
        keys = await client.keys(f"{_CORR_PREFIX}:*")
        if not keys:
            return {}
        values = await client.mget(*keys)
        return {k: v for k, v in zip(keys, values) if v}
