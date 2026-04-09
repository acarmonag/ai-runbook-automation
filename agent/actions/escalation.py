"""
Escalation action — creates escalation records and notifies on-call teams.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

ESCALATION_LOG_FILE = os.environ.get("ESCALATION_LOG_FILE", "escalations.jsonl")
WEBHOOK_URL = os.environ.get("ESCALATION_WEBHOOK_URL", "")


def escalate(reason: str, severity: str) -> dict[str, Any]:
    """
    Create an escalation record and optionally notify via webhook.

    Returns escalation record with ID and timestamp.
    """
    escalation_id = str(uuid.uuid4())[:8]
    timestamp = datetime.now(timezone.utc).isoformat()

    record = {
        "escalation_id": escalation_id,
        "reason": reason,
        "severity": severity,
        "timestamp": timestamp,
        "status": "created",
    }

    logger.warning(
        f"ESCALATION [{escalation_id}] severity={severity}: {reason}"
    )

    # Persist escalation record
    try:
        with open(ESCALATION_LOG_FILE, "a") as f:
            f.write(json.dumps(record) + "\n")
    except OSError as e:
        logger.warning(f"Failed to persist escalation record: {e}")

    # Attempt webhook notification if configured
    if WEBHOOK_URL:
        try:
            import httpx
            payload = {
                "escalation_id": escalation_id,
                "severity": severity,
                "reason": reason,
                "timestamp": timestamp,
            }
            resp = httpx.post(WEBHOOK_URL, json=payload, timeout=5.0)
            resp.raise_for_status()
            record["webhook_notified"] = True
            logger.info(f"Escalation webhook notified: {WEBHOOK_URL}")
        except Exception as e:
            logger.warning(f"Escalation webhook failed (non-fatal): {e}")
            record["webhook_notified"] = False
            record["webhook_error"] = str(e)
    else:
        record["webhook_notified"] = False
        record["message"] = "Set ESCALATION_WEBHOOK_URL to enable webhook notifications"

    return record
