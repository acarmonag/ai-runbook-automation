"""
Incident state machine with structured event emission and persistence.

States: DETECTED → OBSERVING → REASONING → ACTING → VERIFYING → RESOLVED
                                                                 → ESCALATED
                                                                 → FAILED
"""

import json
import logging
import os
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

INCIDENTS_FILE = os.environ.get("INCIDENTS_FILE", "/tmp/incidents.jsonl")


class IncidentState(str, Enum):
    DETECTED = "DETECTED"
    OBSERVING = "OBSERVING"
    REASONING = "REASONING"
    ACTING = "ACTING"
    VERIFYING = "VERIFYING"
    RESOLVED = "RESOLVED"
    ESCALATED = "ESCALATED"
    FAILED = "FAILED"


# Valid transitions
VALID_TRANSITIONS: dict[IncidentState, set[IncidentState]] = {
    IncidentState.DETECTED: {IncidentState.OBSERVING, IncidentState.FAILED},
    IncidentState.OBSERVING: {IncidentState.REASONING, IncidentState.ESCALATED, IncidentState.FAILED},
    IncidentState.REASONING: {
        IncidentState.ACTING,
        IncidentState.VERIFYING,
        IncidentState.RESOLVED,
        IncidentState.ESCALATED,
        IncidentState.FAILED,
    },
    IncidentState.ACTING: {
        IncidentState.REASONING,
        IncidentState.VERIFYING,
        IncidentState.ESCALATED,
        IncidentState.FAILED,
    },
    IncidentState.VERIFYING: {
        IncidentState.REASONING,
        IncidentState.ACTING,
        IncidentState.RESOLVED,
        IncidentState.ESCALATED,
        IncidentState.FAILED,
    },
    IncidentState.RESOLVED: set(),
    IncidentState.ESCALATED: set(),
    IncidentState.FAILED: set(),
}

TERMINAL_STATES = {IncidentState.RESOLVED, IncidentState.ESCALATED, IncidentState.FAILED}


class StateTransitionError(Exception):
    pass


class IncidentStateMachine:
    def __init__(self, incident_id: str, alert: dict[str, Any]):
        self.incident_id = incident_id
        self.alert = alert
        self.state = IncidentState.DETECTED
        self.started_at = datetime.now(timezone.utc)
        self._history: list[dict] = []

        self._record_transition(None, IncidentState.DETECTED)

    def transition(self, new_state: IncidentState) -> None:
        """
        Transition to a new state, validating the transition is allowed.
        Idempotent — transitioning to current state is a no-op.
        """
        if new_state == self.state:
            return

        if self.state in TERMINAL_STATES:
            logger.warning(
                f"[{self.incident_id}] Attempted to transition from terminal state "
                f"{self.state} to {new_state} — ignoring"
            )
            return

        allowed = VALID_TRANSITIONS.get(self.state, set())
        if new_state not in allowed:
            raise StateTransitionError(
                f"Invalid transition: {self.state} → {new_state}. "
                f"Allowed: {allowed}"
            )

        old_state = self.state
        self.state = new_state
        self._record_transition(old_state, new_state)

        logger.info(f"[{self.incident_id}] State: {old_state} → {new_state}")

        if new_state in TERMINAL_STATES:
            self._persist()

    def _record_transition(
        self, from_state: Optional[IncidentState], to_state: IncidentState
    ) -> None:
        event = {
            "incident_id": self.incident_id,
            "from_state": from_state.value if from_state else None,
            "to_state": to_state.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._history.append(event)

    def get_history(self) -> list[dict]:
        return list(self._history)

    def get_duration_seconds(self) -> float:
        return (datetime.now(timezone.utc) - self.started_at).total_seconds()

    def _persist(self) -> None:
        """Append incident summary to incidents.jsonl."""
        try:
            record = {
                "incident_id": self.incident_id,
                "alert_name": self.alert.get("labels", {}).get("alertname", "Unknown"),
                "final_state": self.state.value,
                "started_at": self.started_at.isoformat(),
                "ended_at": datetime.now(timezone.utc).isoformat(),
                "duration_seconds": self.get_duration_seconds(),
                "state_history": self._history,
            }
            with open(INCIDENTS_FILE, "a") as f:
                f.write(json.dumps(record) + "\n")
        except OSError as e:
            logger.warning(f"[{self.incident_id}] Failed to persist incident: {e}")
