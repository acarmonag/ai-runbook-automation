"""
Pydantic models for the runbook automation API.

Matches the Alertmanager webhook payload format exactly.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ─── Alertmanager Webhook Models ─────────────────────────────────────────────

class AlertStatus(str, Enum):
    FIRING = "firing"
    RESOLVED = "resolved"


class AlertLabels(BaseModel):
    alertname: str = "Unknown"
    severity: Optional[str] = None
    service: Optional[str] = None
    instance: Optional[str] = None
    job: Optional[str] = None

    model_config = {"extra": "allow"}


class AlertAnnotations(BaseModel):
    summary: Optional[str] = None
    description: Optional[str] = None
    runbook_url: Optional[str] = None

    model_config = {"extra": "allow"}


class Alert(BaseModel):
    status: AlertStatus = AlertStatus.FIRING
    labels: AlertLabels = Field(default_factory=AlertLabels)
    annotations: AlertAnnotations = Field(default_factory=AlertAnnotations)
    startsAt: Optional[str] = None
    endsAt: Optional[str] = None
    generatorURL: Optional[str] = None
    fingerprint: Optional[str] = None


class AlertmanagerWebhook(BaseModel):
    """Matches Alertmanager webhook payload format exactly."""
    version: str = "4"
    groupKey: Optional[str] = None
    truncatedAlerts: int = 0
    status: AlertStatus = AlertStatus.FIRING
    receiver: str = "agent-webhook"
    groupLabels: dict[str, str] = Field(default_factory=dict)
    commonLabels: dict[str, str] = Field(default_factory=dict)
    commonAnnotations: dict[str, str] = Field(default_factory=dict)
    externalURL: Optional[str] = None
    alerts: list[Alert] = Field(default_factory=list)


# ─── Incident Models ──────────────────────────────────────────────────────────

class IncidentStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    RESOLVED = "RESOLVED"
    ESCALATED = "ESCALATED"
    FAILED = "FAILED"


class ActionRecord(BaseModel):
    action: str
    params: dict[str, Any] = Field(default_factory=dict)
    result: str  # SUCCESS, FAILED, REJECTED, DRY_RUN
    output: Optional[Any] = None
    duration_ms: Optional[int] = None
    timestamp: str


class ReasoningStep(BaseModel):
    role: str  # "assistant" or "user" (tool results)
    content: Any
    timestamp: str


class Incident(BaseModel):
    incident_id: str
    alert_name: str
    alert: dict[str, Any] = Field(default_factory=dict)
    status: IncidentStatus = IncidentStatus.PENDING
    summary: Optional[str] = None
    root_cause: Optional[str] = None
    actions_taken: list[ActionRecord] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    reasoning_transcript: list[ReasoningStep] = Field(default_factory=list)
    state_history: list[dict] = Field(default_factory=list)
    started_at: str
    resolved_at: Optional[str] = None
    full_agent_response: Optional[str] = None


# ─── Approval Models ──────────────────────────────────────────────────────────

class ApprovalRequest(BaseModel):
    incident_id: str
    action: str
    params: dict[str, Any] = Field(default_factory=dict)
    requested_at: str
    reason: Optional[str] = None


class ApprovalResponse(BaseModel):
    incident_id: str
    action: str
    approved: bool
    operator: Optional[str] = None
    reason: Optional[str] = None
    responded_at: str


# ─── API Response Models ──────────────────────────────────────────────────────

class IncidentSummary(BaseModel):
    """Lightweight incident summary for list endpoints."""
    incident_id: str
    alert_name: str
    status: IncidentStatus
    summary: Optional[str] = None
    actions_taken_count: int = 0
    started_at: str
    resolved_at: Optional[str] = None
    duration_seconds: Optional[float] = None


class WebhookResponse(BaseModel):
    message: str
    incidents_queued: int
    incident_ids: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str  # "healthy", "degraded", "unhealthy"
    claude_api: str  # "reachable", "unreachable"
    prometheus: str  # "reachable", "unreachable"
    redis: str = "unknown"  # "reachable", "unreachable"
    queue_depth: int
    active_workers: int
    incidents_processed: int
