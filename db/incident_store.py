"""
Incident persistence layer — all DB writes go through here.

Keeps SQL out of api/ and worker/ code.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Incident

logger = logging.getLogger(__name__)


async def create_incident(session: AsyncSession, data: dict[str, Any]) -> Incident:
    incident = Incident(
        incident_id=data["incident_id"],
        alert_name=data.get("alert_name", "Unknown"),
        alert=data.get("alert", {}),
        status=data.get("status", "PENDING"),
        started_at=datetime.now(timezone.utc),
    )
    session.add(incident)
    await session.commit()
    await session.refresh(incident)
    return incident


async def update_incident(
    session: AsyncSession, incident_id: str, fields: dict[str, Any]
) -> Incident | None:
    fields["updated_at"] = datetime.now(timezone.utc)
    await session.execute(
        update(Incident).where(Incident.incident_id == incident_id).values(**fields)
    )
    await session.commit()
    return await get_incident(session, incident_id)


async def get_incident(session: AsyncSession, incident_id: str) -> Incident | None:
    result = await session.execute(
        select(Incident).where(Incident.incident_id == incident_id)
    )
    return result.scalar_one_or_none()


async def list_incidents(session: AsyncSession) -> list[Incident]:
    result = await session.execute(
        select(Incident).order_by(Incident.started_at.desc())
    )
    return list(result.scalars().all())


async def get_mttr_stats(session: AsyncSession) -> dict[str, Any]:
    """Return aggregate stats for the MTTR dashboard."""
    from sqlalchemy import func as sqlfunc

    result = await session.execute(select(Incident))
    incidents = list(result.scalars().all())

    total = len(incidents)
    resolved = [i for i in incidents if i.status == "RESOLVED" and i.resolved_at]
    escalated = [i for i in incidents if i.status == "ESCALATED"]
    failed = [i for i in incidents if i.status == "FAILED"]

    mttr_seconds: float | None = None
    if resolved:
        durations = [
            (i.resolved_at - i.started_at).total_seconds()
            for i in resolved
            if i.resolved_at and i.started_at
        ]
        mttr_seconds = sum(durations) / len(durations) if durations else None

    by_alert: dict[str, int] = {}
    for i in incidents:
        by_alert[i.alert_name] = by_alert.get(i.alert_name, 0) + 1

    return {
        "total": total,
        "resolved": len(resolved),
        "escalated": len(escalated),
        "failed": len(failed),
        "auto_resolution_rate": round(len(resolved) / total * 100, 1) if total else 0,
        "mttr_seconds": round(mttr_seconds, 1) if mttr_seconds is not None else None,
        "by_alert_name": by_alert,
    }
