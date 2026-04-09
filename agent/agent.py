"""
Main reasoning engine for the AI-powered runbook automation agent.

The agent runs an OBSERVE → REASON → ACT → VERIFY → REPORT loop
using an LLM backend (Ollama or Claude) with tool_use for all actions.

Switch backends via LLM_BACKEND env var:
  LLM_BACKEND=ollama   (default — free, local, qwen3:14b)
  LLM_BACKEND=claude   (Anthropic API — requires ANTHROPIC_API_KEY)
"""

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from agent.actions.registry import ActionRegistry, ActionResult
from agent.approval_gate import ApprovalGate
from agent.llm.base import LLMResponse, ToolCall
from agent.llm.factory import create_backend
from agent.runbook_registry import RunbookRegistry
from agent.state_machine import IncidentStateMachine, IncidentState

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an autonomous SRE (Site Reliability Engineering) automation agent.
Your role is to investigate and remediate production incidents with precision and care.

## Core Responsibilities
- Investigate alerts by collecting system metrics, logs, and service status
- Reason systematically about root causes before taking action
- Execute remediation actions from the approved runbook
- Verify that remediation was successful
- Produce clear incident reports explaining what happened and what you did

## Reasoning Protocol
Before taking ANY action, you must:
1. State what you observe from the current system state
2. Explain your hypothesis about the root cause
3. Describe the action you plan to take and why
4. Predict the expected outcome

## Action Guidelines
- Always collect data BEFORE making changes
- Prefer non-destructive diagnostics over restarts
- Scale UP is safer than scale DOWN — prefer it
- A restart is a last resort after diagnosis
- If uncertain, escalate rather than guess

## Approval Requirements
Destructive actions (restart_service, scale down) require human approval.
You will be informed if an action is pending approval. Do not proceed until approved.

## Verification
After every remediation action, verify the outcome by:
- Re-querying the relevant metrics
- Checking service health status
- Confirming the alert condition has resolved

## Output Format
Always end your investigation with a structured incident report containing:
- incident_id: the ID provided to you
- summary: one-sentence description of what happened
- root_cause: your assessment of the root cause
- actions_taken: list of actions you executed
- outcome: RESOLVED, ESCALATED, or FAILED
- recommendations: any follow-up actions for the team
"""

TOOL_DEFINITIONS = [
    {
        "name": "get_metrics",
        "description": "Run a PromQL query against Prometheus to retrieve current metrics. Use this to check error rates, latency, CPU, memory, and other system metrics.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The PromQL query to execute (e.g., 'rate(http_requests_total{status=~\"5..\"}[5m])')"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_recent_logs",
        "description": "Fetch the most recent log lines from a service container. Use this to look for errors, exceptions, and warnings.",
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "The service/container name to fetch logs from"
                },
                "lines": {
                    "type": "integer",
                    "description": "Number of recent log lines to retrieve (default: 100, max: 500)",
                    "default": 100
                }
            },
            "required": ["service"]
        }
    },
    {
        "name": "get_service_status",
        "description": "Get the current health and runtime status of a service including container state, uptime, and restart count.",
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "The service name to check status for"
                }
            },
            "required": ["service"]
        }
    },
    {
        "name": "scale_service",
        "description": "Scale a service to a specified number of replicas. Scaling UP is non-destructive. Scaling DOWN requires approval.",
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "The service name to scale"
                },
                "replicas": {
                    "type": "integer",
                    "description": "Target number of replicas",
                    "minimum": 0
                }
            },
            "required": ["service", "replicas"]
        }
    },
    {
        "name": "restart_service",
        "description": "Restart a service container. This is a destructive action that requires human approval in AUTO mode. Use only after diagnosis confirms a restart is needed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "The service name to restart"
                }
            },
            "required": ["service"]
        }
    },
    {
        "name": "run_diagnostic",
        "description": "Run a predefined diagnostic check against the system. Safe, read-only operation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "check": {
                    "type": "string",
                    "description": "The diagnostic check to run",
                    "enum": ["disk_usage", "memory_pressure", "connection_count", "error_rate"]
                }
            },
            "required": ["check"]
        }
    },
    {
        "name": "escalate",
        "description": "Escalate this incident to the on-call team when automated remediation cannot resolve the issue.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Clear explanation of why escalation is needed"
                },
                "severity": {
                    "type": "string",
                    "description": "Incident severity level",
                    "enum": ["P1", "P2", "P3", "P4"]
                }
            },
            "required": ["reason", "severity"]
        }
    }
]


class SREAgent:
    """
    Autonomous SRE remediation agent.

    Uses whichever LLM backend is configured via LLM_BACKEND env var.
    Business logic (approval gate, runbooks, state machine, actions) is
    completely backend-agnostic.
    """

    def __init__(
        self,
        action_registry: ActionRegistry,
        runbook_registry: RunbookRegistry,
        approval_gate: ApprovalGate,
        llm_backend=None,
    ):
        self.action_registry = action_registry
        self.runbook_registry = runbook_registry
        self.approval_gate = approval_gate
        # Allow injection for tests; otherwise auto-create from env
        self.llm = llm_backend if llm_backend is not None else create_backend()

    def run(self, alert: dict[str, Any]) -> dict[str, Any]:
        """
        Run the full OBSERVE → REASON → ACT → VERIFY → REPORT loop.
        Returns a structured incident report.
        """
        incident_id = str(uuid.uuid4())[:8]
        alert_name = alert.get("labels", {}).get("alertname", "Unknown")

        logger.info(f"[{incident_id}] Starting agent loop for alert: {alert_name}")

        state_machine = IncidentStateMachine(incident_id=incident_id, alert=alert)
        state_machine.transition(IncidentState.OBSERVING)

        # Load the relevant runbook
        runbook = self.runbook_registry.get_runbook(alert_name)
        runbook_context = ""
        if runbook:
            runbook_context = f"\n\n## Runbook: {runbook.name}\n{runbook.description}\n\nSuggested actions:\n"
            for i, action in enumerate(runbook.actions, 1):
                runbook_context += f"{i}. {action}\n"
        else:
            logger.warning(f"[{incident_id}] No runbook found for alert: {alert_name}")

        initial_message = self._build_initial_message(incident_id, alert, runbook_context)
        messages: list[dict] = [{"role": "user", "content": initial_message}]
        reasoning_transcript: list[dict] = []
        actions_taken: list[dict] = []

        state_machine.transition(IncidentState.REASONING)

        max_iterations = 20
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            logger.debug(f"[{incident_id}] Agent iteration {iteration}")

            try:
                response: LLMResponse = self.llm.chat(
                    system=SYSTEM_PROMPT,
                    messages=messages,
                    tools=TOOL_DEFINITIONS,
                )
            except Exception as e:
                logger.error(f"[{incident_id}] LLM error: {e}")
                state_machine.transition(IncidentState.FAILED)
                return self._build_error_report(incident_id, alert, str(e), actions_taken)

            # Record in transcript
            reasoning_transcript.append({
                "role": "assistant",
                "content": response.raw_assistant_message.get("content"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            # Append to message history (Anthropic format, backend-produced)
            messages.append(response.raw_assistant_message)

            if response.stop_reason == "end_turn":
                logger.info(f"[{incident_id}] Agent completed reasoning")
                state_machine.transition(IncidentState.RESOLVED)
                return self._build_final_report(
                    incident_id, alert, response.text or "",
                    actions_taken, reasoning_transcript, state_machine
                )

            if response.stop_reason != "tool_use" or not response.tool_calls:
                logger.warning(f"[{incident_id}] Unexpected stop: {response.stop_reason}")
                break

            # ─── Process tool calls ────────────────────────────────────────
            tool_results = []
            for tool_call in response.tool_calls:
                state_machine.transition(IncidentState.ACTING)
                tool_name = tool_call.name
                tool_input = tool_call.input

                logger.info(f"[{incident_id}] Tool call: {tool_name}({tool_input})")

                # Check approval for destructive actions
                if self._is_destructive(tool_name, tool_input):
                    approved = self.approval_gate.approve(
                        action=tool_name,
                        params=tool_input,
                        incident_id=incident_id,
                    )
                    if not approved:
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_call.id,
                            "content": json.dumps({
                                "error": "Action rejected by human operator",
                                "action": tool_name,
                            }),
                        })
                        actions_taken.append({
                            "action": tool_name,
                            "params": tool_input,
                            "result": "REJECTED",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })
                        continue

                start_time = time.time()
                result: ActionResult = self.action_registry.execute(
                    action_name=tool_name,
                    params=tool_input,
                    dry_run=self.approval_gate.is_dry_run(),
                )
                duration_ms = int((time.time() - start_time) * 1000)

                actions_taken.append({
                    "action": tool_name,
                    "params": tool_input,
                    "result": "SUCCESS" if result.success else "FAILED",
                    "output": result.output,
                    "duration_ms": duration_ms,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_call.id,
                    "content": json.dumps({
                        "success": result.success,
                        "output": result.output,
                        "duration_ms": duration_ms,
                        "error": result.error,
                    }),
                })

                if tool_name in ("get_metrics", "get_service_status"):
                    state_machine.transition(IncidentState.VERIFYING)
                else:
                    state_machine.transition(IncidentState.REASONING)

            # Append tool results to history (Anthropic format — backends convert)
            messages.append({"role": "user", "content": tool_results})
            reasoning_transcript.append({
                "role": "user",
                "content": tool_results,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

        logger.warning(f"[{incident_id}] Max iterations reached")
        state_machine.transition(IncidentState.ESCALATED)
        return self._build_escalation_report(
            incident_id, alert, actions_taken, reasoning_transcript, state_machine
        )

    # ─── Helpers ──────────────────────────────────────────────────────────────

    def _build_initial_message(
        self, incident_id: str, alert: dict[str, Any], runbook_context: str
    ) -> str:
        labels = alert.get("labels", {})
        annotations = alert.get("annotations", {})
        return f"""## Incident {incident_id}

**Alert:** {labels.get("alertname", "Unknown")}
**Severity:** {labels.get("severity", "unknown")}
**Service:** {labels.get("service", "unknown")}
**Started At:** {alert.get("startsAt", "unknown")}
**Summary:** {annotations.get("summary", "No summary available")}
**Description:** {annotations.get("description", "")}

**Full Alert Labels:**
{json.dumps(labels, indent=2)}

{runbook_context}

Please investigate this incident. Start by collecting relevant metrics and logs, then reason about the root cause, and execute the appropriate remediation actions. After remediating, verify the fix worked.

End your response with a structured JSON incident report in a ```json code block.
"""

    def _is_destructive(self, action_name: str, params: dict) -> bool:
        if action_name == "restart_service":
            return True
        if action_name == "scale_service":
            return params.get("replicas", 999) < 2
        return False

    def _build_final_report(
        self,
        incident_id: str,
        alert: dict,
        final_text: str,
        actions_taken: list,
        reasoning_transcript: list,
        state_machine: IncidentStateMachine,
    ) -> dict:
        structured = self._extract_json_report(final_text)
        return {
            "incident_id": incident_id,
            "alert_name": alert.get("labels", {}).get("alertname", "Unknown"),
            "alert": alert,
            "status": structured.get("outcome", "RESOLVED"),
            "summary": structured.get("summary", final_text[:200]),
            "root_cause": structured.get("root_cause", ""),
            "actions_taken": actions_taken,
            "recommendations": structured.get("recommendations", []),
            "reasoning_transcript": reasoning_transcript,
            "state_history": state_machine.get_history(),
            "started_at": state_machine.started_at.isoformat(),
            "resolved_at": datetime.now(timezone.utc).isoformat(),
            "full_agent_response": final_text,
        }

    def _build_error_report(
        self, incident_id: str, alert: dict, error: str, actions_taken: list
    ) -> dict:
        return {
            "incident_id": incident_id,
            "alert_name": alert.get("labels", {}).get("alertname", "Unknown"),
            "alert": alert,
            "status": "FAILED",
            "summary": f"Agent failed: {error}",
            "root_cause": "Agent runtime error",
            "actions_taken": actions_taken,
            "recommendations": ["Investigate agent error", "Review LLM connectivity"],
            "reasoning_transcript": [],
            "state_history": [],
            "started_at": datetime.now(timezone.utc).isoformat(),
            "resolved_at": datetime.now(timezone.utc).isoformat(),
            "full_agent_response": error,
        }

    def _build_escalation_report(
        self,
        incident_id: str,
        alert: dict,
        actions_taken: list,
        reasoning_transcript: list,
        state_machine: IncidentStateMachine,
    ) -> dict:
        return {
            "incident_id": incident_id,
            "alert_name": alert.get("labels", {}).get("alertname", "Unknown"),
            "alert": alert,
            "status": "ESCALATED",
            "summary": "Agent reached maximum iterations without resolving",
            "root_cause": "Could not determine root cause automatically",
            "actions_taken": actions_taken,
            "recommendations": ["Manual investigation required"],
            "reasoning_transcript": reasoning_transcript,
            "state_history": state_machine.get_history(),
            "started_at": state_machine.started_at.isoformat(),
            "resolved_at": datetime.now(timezone.utc).isoformat(),
            "full_agent_response": "",
        }

    def _extract_json_report(self, text: str) -> dict:
        import re
        for match in re.findall(r"```json\s*(.*?)\s*```", text, re.DOTALL):
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                continue
        return {}
