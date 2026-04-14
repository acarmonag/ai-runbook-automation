"""
Stateful scenario tracking for mock Prometheus.

Phases per scenario:
  INCIDENT    — alert is firing, metrics are degraded
  REMEDIATING — remediation action received, metrics partially recovering
  RECOVERED   — metrics are back to normal, alert resolved

Transitions are triggered via the POST /api/v1/remediation endpoint.
"""

import threading
import time

_lock = threading.Lock()

# Phase constants
PHASE_INCIDENT = "INCIDENT"
PHASE_REMEDIATING = "REMEDIATING"
PHASE_RECOVERED = "RECOVERED"

# State: scenario_name → {"phase": str, "remediated_at": float}
_state: dict[str, dict] = {}


def get_phase(scenario: str) -> str:
    with _lock:
        return _state.get(scenario, {}).get("phase", PHASE_INCIDENT)


def trigger_remediation(scenario: str, action: str) -> dict:
    """
    Record that a remediation action was taken.
    Transitions: INCIDENT → REMEDIATING → RECOVERED (after 5 s).
    """
    with _lock:
        entry = _state.get(scenario, {"phase": PHASE_INCIDENT})
        if entry["phase"] == PHASE_INCIDENT:
            _state[scenario] = {
                "phase": PHASE_REMEDIATING,
                "remediated_at": time.time(),
                "action": action,
            }
        elif entry["phase"] == PHASE_REMEDIATING:
            # Second remediation call (e.g. verify after restart) → fully recovered
            _state[scenario] = {
                "phase": PHASE_RECOVERED,
                "remediated_at": entry.get("remediated_at", time.time()),
                "action": action,
            }
        return {"scenario": scenario, "phase": _state[scenario]["phase"]}


def maybe_auto_advance(scenario: str) -> None:
    """
    Auto-advance REMEDIATING → RECOVERED after 5 seconds.
    Call this before reading metrics so queries after remediation see recovery.
    """
    with _lock:
        entry = _state.get(scenario)
        if entry and entry["phase"] == PHASE_REMEDIATING:
            elapsed = time.time() - entry.get("remediated_at", 0)
            if elapsed >= 5:
                _state[scenario]["phase"] = PHASE_RECOVERED


def reset(scenario: str) -> None:
    """Reset scenario back to INCIDENT (for testing/re-runs)."""
    with _lock:
        _state[scenario] = {"phase": PHASE_INCIDENT}
