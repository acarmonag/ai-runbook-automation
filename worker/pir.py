"""
Post-Incident Review (PIR) auto-generation.

Called after a RESOLVED incident — uses the LLM to turn the raw incident
data into a structured review document and persists it to PostgreSQL.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

PIR_PROMPT = """You are an SRE writing a Post-Incident Review (PIR).

Given the following incident data, produce a structured PIR in JSON with these fields:
- title: one-line summary
- severity: P1/P2/P3/P4
- timeline: list of {{ time, event }} items derived from state_history and actions_taken
- root_cause: concise technical root cause (2-3 sentences)
- contributing_factors: list of strings
- impact: what was affected and for how long
- resolution: what fixed it
- action_items: list of {{ owner, action, priority }} follow-up tasks
- prevention: list of preventive measures for the future

Respond ONLY with valid JSON. No markdown fences.

Incident data:
{incident_json}
"""


async def generate_pir(incident_id: str, report: dict[str, Any]) -> None:
    """Generate and persist a PIR for a resolved incident."""
    import json
    from agent.llm.factory import create_backend
    from db.database import AsyncSessionLocal
    from db.incident_store import update_incident

    try:
        backend = create_backend()
        prompt = PIR_PROMPT.format(
            incident_json=json.dumps({
                "alert_name": report.get("alert_name"),
                "root_cause": report.get("root_cause"),
                "summary": report.get("summary"),
                "actions_taken": report.get("actions_taken", []),
                "recommendations": report.get("recommendations", []),
                "state_history": report.get("state_history", []),
            }, indent=2)
        )

        response = backend.chat(
            system="You are an expert SRE writing Post-Incident Reviews.",
            messages=[{"role": "user", "content": prompt}],
            tools=[],
        )

        pir_text = response.text or ""
        # Strip markdown fences if the model added them
        pir_text = pir_text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()

        pir_data = json.loads(pir_text)

        async with AsyncSessionLocal() as session:
            await update_incident(session, incident_id, {"pir": pir_data})

        logger.info(f"[{incident_id}] PIR generated successfully")

    except Exception as exc:
        logger.warning(f"[{incident_id}] PIR generation failed: {exc}")
