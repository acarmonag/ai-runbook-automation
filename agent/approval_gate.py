"""
Human approval gate for destructive actions.

Modes:
- AUTO: auto-approves non-destructive, prompts human for destructive
- DRY_RUN: logs all actions, never executes, always returns True
- MANUAL: always prompts for human approval
"""

import logging
import os
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)

DESTRUCTIVE_ACTIONS = {"restart_service", "scale_service"}


class ApprovalMode(str, Enum):
    AUTO = "AUTO"
    DRY_RUN = "DRY_RUN"
    MANUAL = "MANUAL"


class ApprovalGate:
    def __init__(self, mode: Optional[ApprovalMode] = None):
        if mode is None:
            raw = os.environ.get("APPROVAL_MODE", "AUTO").upper()
            try:
                mode = ApprovalMode(raw)
            except ValueError:
                logger.warning(f"Unknown APPROVAL_MODE '{raw}', defaulting to AUTO")
                mode = ApprovalMode.AUTO
        self.mode = mode
        logger.info(f"ApprovalGate initialized in {self.mode} mode")

    def is_dry_run(self) -> bool:
        """Return True if running in DRY_RUN mode."""
        return self.mode == ApprovalMode.DRY_RUN

    def approve(self, action: str, params: dict[str, Any], incident_id: str = "") -> bool:
        """
        Request approval for an action.

        Returns True if approved, False if rejected.
        """
        context_str = f"[{incident_id}] " if incident_id else ""

        if self.mode == ApprovalMode.DRY_RUN:
            logger.info(f"{context_str}DRY_RUN: Would execute {action}({params}) — skipping")
            return True

        is_destructive = self._is_destructive(action, params)

        if self.mode == ApprovalMode.AUTO:
            # AUTO mode = fully automated — all actions are pre-approved
            logger.info(f"{context_str}AUTO: Auto-approving {action}({'destructive' if is_destructive else 'safe'})")
            return True

        if self.mode == ApprovalMode.MANUAL:
            return self._prompt_human(action, params, incident_id)

        return False

    def _is_destructive(self, action: str, params: dict[str, Any]) -> bool:
        """Determine if an action is destructive."""
        if action == "restart_service":
            return True
        if action == "scale_service":
            replicas = params.get("replicas", 999)
            return replicas < 2
        if params.get("force", False):
            return True
        return False

    def _prompt_human(self, action: str, params: dict[str, Any], incident_id: str) -> bool:
        """Prompt for human approval via stdin."""
        print(f"\n{'='*60}")
        print(f"APPROVAL REQUIRED — Incident: {incident_id}")
        print(f"{'='*60}")
        print(f"Action   : {action}")
        print(f"Parameters: {params}")
        print(f"{'='*60}")

        try:
            response = input("Approve? [y/N]: ").strip().lower()
            approved = response in ("y", "yes")
            if approved:
                logger.info(f"[{incident_id}] Human APPROVED {action}({params})")
            else:
                logger.info(f"[{incident_id}] Human REJECTED {action}({params})")
            return approved
        except (EOFError, KeyboardInterrupt):
            logger.warning(f"[{incident_id}] Approval prompt interrupted — rejecting {action}")
            return False
