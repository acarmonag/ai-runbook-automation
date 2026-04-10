"""
Escalation action — notifies Slack and/or PagerDuty when automated
remediation cannot resolve an incident.

Configuration via environment variables:
  SLACK_WEBHOOK_URL        Incoming webhook URL (slack.com/api/…)
  PAGERDUTY_ROUTING_KEY    PagerDuty Events v2 routing key
  ESCALATION_LOG_FILE      Local JSONL fallback (default: escalations.jsonl)
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

ESCALATION_LOG_FILE = os.environ.get("ESCALATION_LOG_FILE", "escalations.jsonl")
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")
PAGERDUTY_ROUTING_KEY = os.environ.get("PAGERDUTY_ROUTING_KEY", "")
PAGERDUTY_EVENTS_URL = "https://events.pagerduty.com/v2/enqueue"

_SEVERITY_EMOJI = {"P1": "🔴", "P2": "🟠", "P3": "🟡", "P4": "🔵"}
_PD_SEVERITY = {"P1": "critical", "P2": "error", "P3": "warning", "P4": "info"}


def escalate(reason: str, severity: str) -> dict[str, Any]:
    """
    Escalate an incident to the on-call team via Slack and/or PagerDuty.
    Falls back to a local JSONL log if no webhooks are configured.
    """
    escalation_id = str(uuid.uuid4())[:8]
    timestamp = datetime.now(timezone.utc).isoformat()

    record: dict[str, Any] = {
        "escalation_id": escalation_id,
        "reason": reason,
        "severity": severity,
        "timestamp": timestamp,
        "channels": [],
    }

    logger.warning("ESCALATION [%s] severity=%s: %s", escalation_id, severity, reason)

    # ── Slack ──────────────────────────────────────────────────────────────
    if SLACK_WEBHOOK_URL:
        try:
            _notify_slack(escalation_id, reason, severity, timestamp)
            record["channels"].append("slack")
        except Exception as exc:
            logger.warning("Slack escalation failed: %s", exc)
            record["slack_error"] = str(exc)

    # ── PagerDuty ──────────────────────────────────────────────────────────
    if PAGERDUTY_ROUTING_KEY:
        try:
            pd_incident_key = _notify_pagerduty(
                escalation_id, reason, severity, timestamp
            )
            record["channels"].append("pagerduty")
            record["pagerduty_incident_key"] = pd_incident_key
        except Exception as exc:
            logger.warning("PagerDuty escalation failed: %s", exc)
            record["pagerduty_error"] = str(exc)

    if not record["channels"]:
        record["message"] = (
            "No notification channels configured. "
            "Set SLACK_WEBHOOK_URL and/or PAGERDUTY_ROUTING_KEY."
        )
        logger.info("Escalation logged locally only (no webhook configured)")

    # ── Local log fallback ─────────────────────────────────────────────────
    try:
        with open(ESCALATION_LOG_FILE, "a") as f:
            f.write(json.dumps(record) + "\n")
    except OSError as exc:
        logger.debug("Could not write escalation log: %s", exc)

    return record


def _notify_slack(
    escalation_id: str, reason: str, severity: str, timestamp: str
) -> None:
    """Post a rich Slack message via incoming webhook."""
    import httpx

    emoji = _SEVERITY_EMOJI.get(severity, "⚠️")
    payload = {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} Incident Escalation — {severity}",
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Escalation ID:*\n`{escalation_id}`"},
                    {"type": "mrkdwn", "text": f"*Severity:*\n{severity}"},
                ],
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Reason:*\n{reason}"},
            },
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f"Triggered at {timestamp}"}],
            },
        ]
    }
    resp = httpx.post(SLACK_WEBHOOK_URL, json=payload, timeout=5.0)
    resp.raise_for_status()
    logger.info("Slack escalation sent [%s]", escalation_id)


def _notify_pagerduty(
    escalation_id: str, reason: str, severity: str, timestamp: str
) -> str:
    """Create a PagerDuty alert via Events API v2. Returns the dedup key."""
    import httpx

    pd_severity = _PD_SEVERITY.get(severity, "error")
    payload = {
        "routing_key": PAGERDUTY_ROUTING_KEY,
        "event_action": "trigger",
        "dedup_key": escalation_id,
        "payload": {
            "summary": reason,
            "severity": pd_severity,
            "source": "sre-runbook-agent",
            "timestamp": timestamp,
            "custom_details": {
                "escalation_id": escalation_id,
                "severity": severity,
            },
        },
    }
    resp = httpx.post(PAGERDUTY_EVENTS_URL, json=payload, timeout=5.0)
    resp.raise_for_status()
    dedup_key = resp.json().get("dedup_key", escalation_id)
    logger.info("PagerDuty alert created [%s] key=%s", escalation_id, dedup_key)
    return dedup_key
