"""
Human approval gate for destructive actions.

Modes:
- AUTO:    auto-approves everything — agent runs fully autonomously
- DRY_RUN: logs all actions, never executes, always returns True
- MANUAL:  pauses on destructive actions, publishes a PENDING_APPROVAL event to
           Redis, then polls indefinitely for a human decision (approve / reject
           via the UI). The agent stays on hold until the operator responds.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)

DESTRUCTIVE_ACTIONS  = {"restart_service", "scale_service"}
_PENDING_KEY_TTL_S   = 86400  # keep the pending key in Redis for up to 24h (no polling timeout)
_POLL_INTERVAL_S     = 2


class ApprovalMode(str, Enum):
    AUTO    = "AUTO"
    DRY_RUN = "DRY_RUN"
    MANUAL  = "MANUAL"


class ApprovalGate:
    def __init__(
        self,
        mode: Optional[ApprovalMode] = None,
        redis_url: Optional[str] = None,
    ):
        if mode is None:
            raw = os.environ.get("APPROVAL_MODE", "AUTO").upper()
            try:
                mode = ApprovalMode(raw)
            except ValueError:
                logger.warning(f"Unknown APPROVAL_MODE '{raw}', defaulting to AUTO")
                mode = ApprovalMode.AUTO
        self.mode = mode
        self._redis_url = redis_url or os.environ.get("REDIS_URL", "redis://localhost:6379")
        logger.info(f"ApprovalGate initialized in {self.mode} mode")

    def is_dry_run(self) -> bool:
        return self.mode == ApprovalMode.DRY_RUN

    def approve(
        self,
        action: str,
        params: dict[str, Any],
        incident_id: str = "",
        sre_insight: Optional[dict[str, Any]] = None,
    ) -> bool:
        """
        Request approval for an action.
        Returns True if approved, False if rejected or timed out.
        """
        context = f"[{incident_id}] " if incident_id else ""

        if self.mode == ApprovalMode.DRY_RUN:
            logger.info(f"{context}DRY_RUN: skipping {action}({params})")
            return True

        if self.mode == ApprovalMode.AUTO:
            logger.info(f"{context}AUTO: approving {action}")
            return True

        if self.mode == ApprovalMode.MANUAL:
            if not self._is_destructive(action, params):
                logger.info(f"{context}MANUAL: auto-approving non-destructive {action}")
                return True
            return self._wait_for_human(action, params, incident_id, sre_insight or {})

        return False

    # ── Private ───────────────────────────────────────────────────────────────

    def _is_destructive(self, action: str, params: dict[str, Any]) -> bool:
        if action == "restart_service":
            return True
        if action == "scale_service":
            return params.get("replicas", 999) < 2
        if params.get("force", False):
            return True
        return False

    def _wait_for_human(
        self,
        action: str,
        params: dict[str, Any],
        incident_id: str,
        sre_insight: dict[str, Any],
    ) -> bool:
        """
        Publish a PENDING_APPROVAL event to Redis pub/sub, then poll
        `approval_decision:{incident_id}` until approved, rejected, or timeout.
        """
        try:
            import redis as _redis
            r = _redis.from_url(self._redis_url, socket_connect_timeout=3, decode_responses=True)
        except Exception as exc:
            logger.error(f"ApprovalGate: cannot connect to Redis — auto-rejecting: {exc}")
            return False

        pending_key  = f"approval_pending:{incident_id}"
        decision_key = f"approval_decision:{incident_id}"
        requested_at = datetime.now(timezone.utc).isoformat()

        payload = {
            "incident_id":  incident_id,
            "status":       "PENDING_APPROVAL",
            "pending_action": action,
            "params":       params,
            "sre_insight":  sre_insight,
            "requested_at": requested_at,
        }

        try:
            r.setex(pending_key, _PENDING_KEY_TTL_S, json.dumps(payload))
            r.publish("incident_updates", json.dumps(payload))
            logger.info(f"[{incident_id}] MANUAL: published PENDING_APPROVAL for {action} — waiting indefinitely for human decision")
        except Exception as exc:
            logger.error(f"[{incident_id}] Failed to publish approval request: {exc}")
            return False

        # Poll indefinitely — no timeout.  Agent stays on hold until operator responds.
        while True:
            try:
                decision = r.get(decision_key)
            except Exception:
                decision = None

            if decision:
                approved = str(decision).upper() == "APPROVED"
                logger.info(
                    f"[{incident_id}] Human {'APPROVED' if approved else 'REJECTED'} {action}"
                )
                try:
                    r.delete(decision_key)
                    r.delete(pending_key)
                except Exception:
                    pass
                return approved

            time.sleep(_POLL_INTERVAL_S)
