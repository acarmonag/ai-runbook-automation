"""
SQLAlchemy ORM models.

All JSON columns store Python dicts/lists directly — asyncpg handles
serialisation transparently.
"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Incident(Base):
    __tablename__ = "incidents"

    incident_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    alert_name: Mapped[str] = mapped_column(String(255), nullable=False)
    alert: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="PENDING")
    summary: Mapped[str | None] = mapped_column(Text)
    root_cause: Mapped[str | None] = mapped_column(Text)
    actions_taken: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    recommendations: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    reasoning_transcript: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    state_history: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    pending_action: Mapped[str | None] = mapped_column(String(255))
    approval_state: Mapped[str | None] = mapped_column(String(50))
    # PIR auto-generated after resolution
    pir: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # LLM usage tracking
    llm_tokens_used: Mapped[int | None] = mapped_column()
    llm_model: Mapped[str | None] = mapped_column(String(100))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    full_agent_response: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "alert_name": self.alert_name,
            "alert": self.alert or {},
            "status": self.status,
            "summary": self.summary,
            "root_cause": self.root_cause,
            "actions_taken": self.actions_taken or [],
            "recommendations": self.recommendations or [],
            "reasoning_transcript": self.reasoning_transcript or [],
            "state_history": self.state_history or [],
            "pending_action": self.pending_action,
            "approval_state": self.approval_state,
            "pir": self.pir,
            "llm_tokens_used": self.llm_tokens_used,
            "llm_model": self.llm_model,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "full_agent_response": self.full_agent_response,
        }
