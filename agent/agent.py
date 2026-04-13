"""
Main reasoning engine for the AI-powered runbook automation agent.

The agent runs an OBSERVE → REASON → ACT → VERIFY → REPORT loop
using an LLM backend (Ollama or Claude) with tool_use for all actions.

Switch backends via LLM_BACKEND env var:
  LLM_BACKEND=ollama   (default — free, local, qwen3:14b)
  LLM_BACKEND=claude   (Anthropic API — requires ANTHROPIC_API_KEY)
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from agent.actions.registry import ActionRegistry, ActionResult
from agent.approval_gate import ApprovalGate
from agent.llm.base import LLMResponse, ToolCall
from agent.llm.factory import create_backend
from agent.runbook_registry import RunbookRegistry
from agent.state_machine import IncidentStateMachine, IncidentState

logger = logging.getLogger(__name__)

_LLM_MAX_RETRIES = 3
_LLM_RETRY_DELAYS = [2, 5, 10]  # seconds between retries

SYSTEM_PROMPT = """You are an autonomous SRE agent. Investigate and remediate production incidents by calling tools, not by writing instructions.

RESPONSE FORMAT — CRITICAL
Write plain prose only. No markdown: no headers, no bold, no bullet lists, no numbered lists, no code blocks, no backticks around commands. Keep any text you write to 1-3 short sentences that state what you observed and what you will do next. Then call the appropriate tool immediately. Never write shell commands or docker commands — use the provided tools instead.

WORKFLOW
Observe: call get_metrics, get_recent_logs, get_service_status to collect data.
Reason: one sentence stating the likely root cause based on what you observed.
Act: call the appropriate tool (restart_service, scale_service, run_diagnostic, escalate).
Verify: after any remediation, call get_metrics and run_diagnostic with check=alert_status.
Report: call complete_incident with the structured report. Never write the report as text.

ACTION RULES
All actions are pre-approved in AUTO mode. Call tools directly — never ask for permission.
Always collect data before making changes.
A restart is correct for: crashes, memory leaks, high error rates, CPU spikes.
If a tool returns an error, note it briefly and continue — do not escalate on a single tool failure.
After restart_service or scale_service, always re-check metrics and run alert_status diagnostic.

RESOLUTION — declare RESOLVED when after remediation any of these is true:
run_diagnostic alert_status returns alert_firing false, error rate below 1%, latency below 1s, memory below 500MB, CPU below 50%.

ESCALATION — only if all of these are true:
At least 3 diagnostic tools have been called, remediation failed or was rejected, no improvement in metrics, root cause cannot be determined.

FINISHING — call complete_incident when done. This is mandatory.
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
        "description": "Run a predefined diagnostic check against the system. Safe, read-only operation. Use 'alert_status' AFTER every remediation action to verify the alert resolved.",
        "input_schema": {
            "type": "object",
            "properties": {
                "check": {
                    "type": "string",
                    "description": "The diagnostic check to run",
                    "enum": ["disk_usage", "memory_pressure", "connection_count", "error_rate", "alert_status"]
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
    },
    {
        "name": "complete_incident",
        "description": "REQUIRED: Call this tool to finalize the incident and submit your investigation report. You MUST call this tool — do not write the report as text. Call this as the very last action after all investigation and verification is complete.",
        "input_schema": {
            "type": "object",
            "properties": {
                "outcome": {
                    "type": "string",
                    "description": "Final outcome of the incident",
                    "enum": ["RESOLVED", "ESCALATED", "FAILED"]
                },
                "summary": {
                    "type": "string",
                    "description": "One-sentence summary of what happened and how it was resolved"
                },
                "root_cause": {
                    "type": "string",
                    "description": "Your diagnosis of the root cause"
                },
                "actions_taken": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of actions you executed (e.g. 'Restarted api service to clear connection pool')"
                },
                "recommendations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Follow-up recommendations for the team"
                }
            },
            "required": ["outcome", "summary", "root_cause", "actions_taken", "recommendations"]
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
            if runbook.verification:
                resolved_when = runbook.verification.get("resolved_when", [])
                escalate_when = runbook.verification.get("escalate_when", [])
                if resolved_when:
                    runbook_context += "\n**Resolution Criteria (declare RESOLVED when any of these is true):**\n"
                    for criterion in resolved_when:
                        runbook_context += f"- {criterion}\n"
                if escalate_when:
                    runbook_context += "\n**Escalation Criteria:**\n"
                    for criterion in escalate_when:
                        runbook_context += f"- {criterion}\n"
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

            response = self._llm_with_retry(incident_id, messages)
            if response is None:
                state_machine.transition(IncidentState.FAILED)
                return self._build_error_report(
                    incident_id, alert,
                    "LLM unreachable after retries — check Ollama/Claude connectivity",
                    actions_taken,
                    reasoning_transcript,
                )

            # Record in transcript
            reasoning_transcript.append({
                "role": "assistant",
                "content": response.raw_assistant_message.get("content"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            # Append to message history (Anthropic format, backend-produced)
            messages.append(response.raw_assistant_message)

            if response.stop_reason == "end_turn":
                # Check if the agent skipped remediation (wrote analysis but didn't act).
                remediation_actions = {"restart_service", "scale_service", "escalate", "complete_incident"}
                has_remediated = any(a.get("action") in remediation_actions for a in actions_taken)

                if not has_remediated and iteration <= 3:
                    # Push the agent to proceed with the runbook action instead of just analyzing.
                    logger.info(f"[{incident_id}] Agent wrote analysis without acting — pushing to execute runbook")
                    nudge = (
                        "You have completed your analysis. Good. Now you MUST proceed with the runbook action. "
                        "Do not write more analysis — call the appropriate tool to remediate the incident. "
                        "In AUTO mode all actions are pre-approved. Execute restart_service or scale_service now."
                    )
                    messages.append({"role": "user", "content": nudge})
                    reasoning_transcript.append({
                        "role": "user",
                        "content": nudge,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                    continue

                logger.info(f"[{incident_id}] Agent completed reasoning")
                state_machine.transition(IncidentState.RESOLVED)
                return self._build_final_report(
                    incident_id, alert, response.text or "",
                    actions_taken, reasoning_transcript, state_machine
                )

            if response.stop_reason != "tool_use" or not response.tool_calls:
                logger.warning(f"[{incident_id}] Unexpected stop: {response.stop_reason}")
                break

            # ─── Check for complete_incident (terminal tool) ──────────────
            terminal = next(
                (tc for tc in response.tool_calls if tc.name == "complete_incident"), None
            )
            if terminal:
                report = terminal.input
                state_machine.transition(IncidentState.RESOLVED)
                escalated = any(a.get("action") == "escalate" for a in actions_taken)
                outcome = report.get("outcome") or ("ESCALATED" if escalated else "RESOLVED")
                return {
                    "incident_id": incident_id,
                    "alert_name": alert.get("labels", {}).get("alertname", "Unknown"),
                    "alert": alert,
                    "status": outcome,
                    "summary": report.get("summary", ""),
                    "root_cause": report.get("root_cause", ""),
                    "actions_taken": actions_taken,
                    "recommendations": report.get("recommendations", []),
                    "reasoning_transcript": reasoning_transcript,
                    "state_history": state_machine.get_history(),
                    "started_at": state_machine.started_at.isoformat(),
                    "resolved_at": datetime.now(timezone.utc).isoformat(),
                    "full_agent_response": json.dumps(report),
                }

            # ─── Process regular tool calls ───────────────────────────────
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

    def _llm_with_retry(
        self, incident_id: str, messages: list[dict]
    ) -> LLMResponse | None:
        """Call the LLM with exponential backoff. Returns None if all retries fail."""
        last_exc: Exception | None = None
        for attempt in range(_LLM_MAX_RETRIES):
            try:
                return self.llm.chat(
                    system=SYSTEM_PROMPT,
                    messages=messages,
                    tools=TOOL_DEFINITIONS,
                )
            except Exception as exc:
                last_exc = exc
                delay = _LLM_RETRY_DELAYS[attempt]
                logger.warning(
                    f"[{incident_id}] LLM error (attempt {attempt + 1}/{_LLM_MAX_RETRIES}): {exc} — retrying in {delay}s"
                )
                time.sleep(delay)

        logger.error(f"[{incident_id}] All LLM retries exhausted. Last error: {last_exc}")
        return None

    def _build_initial_message(
        self, incident_id: str, alert: dict[str, Any], runbook_context: str
    ) -> str:
        labels = alert.get("labels", {})
        annotations = alert.get("annotations", {})
        description = annotations.get("description", "").strip()
        return (
            f"Incident {incident_id}\n"
            f"Alert: {labels.get('alertname', 'Unknown')} | "
            f"Severity: {labels.get('severity', 'unknown')} | "
            f"Service: {labels.get('service', 'unknown')}\n"
            f"Summary: {annotations.get('summary', 'No summary available')}\n"
            + (f"Details: {description}\n" if description else "")
            + f"\n{runbook_context}\n"
            "Begin investigation. Call tools to collect data, then remediate. "
            "All actions are pre-approved. When done call complete_incident."
        )

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

        # Derive outcome: prefer parsed report, then check if escalate was called,
        # then fall back to RESOLVED.
        escalated = any(a.get("action") == "escalate" for a in actions_taken)
        outcome = structured.get("outcome") or ("ESCALATED" if escalated else "RESOLVED")

        return {
            "incident_id": incident_id,
            "alert_name": alert.get("labels", {}).get("alertname", "Unknown"),
            "alert": alert,
            "status": outcome,
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
        self, incident_id: str, alert: dict, error: str, actions_taken: list,
        reasoning_transcript: Optional[list] = None,
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
            "reasoning_transcript": reasoning_transcript or [],
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

        # 1. Try ```json ... ``` code block
        for match in re.findall(r"```json\s*(.*?)\s*```", text, re.DOTALL):
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                continue

        # 2. Try <incident_report>...</incident_report> XML
        xml_match = re.search(r"<incident_report>(.*?)</incident_report>", text, re.DOTALL | re.IGNORECASE)
        if xml_match:
            xml = xml_match.group(0)

            def _field(tag: str) -> str:
                m = re.search(rf"<{tag}>(.*?)</{tag}>", xml, re.DOTALL | re.IGNORECASE)
                return m.group(1).strip() if m else ""

            def _list(container: str, item: str) -> list[str]:
                c = re.search(rf"<{container}>(.*?)</{container}>", xml, re.DOTALL | re.IGNORECASE)
                if not c:
                    return []
                return [m.group(1).strip() for m in re.finditer(rf"<{item}>(.*?)</{item}>", c.group(1), re.DOTALL | re.IGNORECASE)]

            return {
                "outcome": _field("outcome") or None,
                "summary": _field("summary") or None,
                "root_cause": _field("root_cause") or None,
                "recommendations": _list("recommendations", "recommendation"),
            }

        return {}
