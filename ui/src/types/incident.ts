export type IncidentStatus =
  | "PENDING"
  | "PROCESSING"
  | "RESOLVED"
  | "ESCALATED"
  | "FAILED"
  // State machine states surfaced in detail view
  | "DETECTED"
  | "OBSERVING"
  | "REASONING"
  | "ACTING"
  | "VERIFYING";

export type ActionResult = "SUCCESS" | "FAILED" | "REJECTED" | "DRY_RUN" | "SKIPPED";

export interface ActionTaken {
  action: string;
  params: Record<string, unknown>;
  result: ActionResult;
  output: unknown;
  duration_ms?: number;
  timestamp: string;
}

export type ContentBlock =
  | { type: "text"; text: string }
  | { type: "tool_use"; id: string; name: string; input: Record<string, unknown> }
  | { type: "tool_result"; tool_use_id: string; content: string };

export interface TranscriptMessage {
  role: "user" | "assistant" | "system";
  content: string | ContentBlock[];
  timestamp?: string;
}

export interface IncidentSummary {
  incident_id: string;
  alert_name: string;
  status: IncidentStatus;
  summary?: string;
  actions_taken_count: number;
  started_at: string;
  resolved_at?: string;
  duration_seconds?: number;
}

export interface Incident {
  incident_id: string;
  alert_name: string;
  alert: Record<string, unknown>;
  status: IncidentStatus;
  summary?: string;
  root_cause?: string;
  actions_taken: ActionTaken[];
  recommendations: string[];
  reasoning_transcript: TranscriptMessage[];
  state_history: { state: string; timestamp: string; event?: string }[];
  started_at: string;
  resolved_at?: string;
  full_agent_response?: string;
  pending_action?: string;
  approval_state?: "PENDING" | "APPROVED" | "REJECTED";
}

export interface WebhookResponse {
  message: string;
  incidents_queued: number;
  incident_ids: string[];
}
