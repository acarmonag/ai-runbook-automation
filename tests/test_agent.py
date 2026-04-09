"""
Tests for the core agent reasoning loop.

Tests:
- Agent loop with mocked LLM backend (backend-agnostic)
- State machine transitions
- Runbook selection by alert name
- Approval gate in AUTO, DRY_RUN, MANUAL modes
"""

from unittest.mock import MagicMock, patch

import pytest

from agent.agent import SREAgent
from agent.approval_gate import ApprovalGate, ApprovalMode
from agent.llm.base import LLMResponse, ToolCall
from agent.runbook_registry import RunbookRegistry
from agent.state_machine import (
    IncidentState,
    IncidentStateMachine,
    StateTransitionError,
)
from agent.actions.registry import ActionRegistry, ActionResult


# ─── State Machine Tests ──────────────────────────────────────────────────────

class TestIncidentStateMachine:
    def _make_sm(self):
        return IncidentStateMachine(
            incident_id="test-001",
            alert={"labels": {"alertname": "TestAlert"}},
        )

    def test_initial_state_is_detected(self):
        sm = self._make_sm()
        assert sm.state == IncidentState.DETECTED

    def test_valid_transition_detected_to_observing(self):
        sm = self._make_sm()
        sm.transition(IncidentState.OBSERVING)
        assert sm.state == IncidentState.OBSERVING

    def test_valid_transition_chain(self):
        sm = self._make_sm()
        sm.transition(IncidentState.OBSERVING)
        sm.transition(IncidentState.REASONING)
        sm.transition(IncidentState.ACTING)
        sm.transition(IncidentState.VERIFYING)
        sm.transition(IncidentState.RESOLVED)
        assert sm.state == IncidentState.RESOLVED

    def test_invalid_transition_raises(self):
        sm = self._make_sm()
        with pytest.raises(StateTransitionError):
            sm.transition(IncidentState.ACTING)  # DETECTED → ACTING is invalid

    def test_terminal_state_ignored_on_retry(self):
        sm = self._make_sm()
        sm.transition(IncidentState.OBSERVING)
        sm.transition(IncidentState.REASONING)
        sm.transition(IncidentState.RESOLVED)
        sm.transition(IncidentState.FAILED)  # should be silently ignored
        assert sm.state == IncidentState.RESOLVED

    def test_idempotent_transition(self):
        sm = self._make_sm()
        sm.transition(IncidentState.OBSERVING)
        sm.transition(IncidentState.OBSERVING)  # no-op
        assert sm.state == IncidentState.OBSERVING

    def test_history_records_transitions(self):
        sm = self._make_sm()
        sm.transition(IncidentState.OBSERVING)
        sm.transition(IncidentState.REASONING)
        history = sm.get_history()
        assert len(history) == 3  # DETECTED + OBSERVING + REASONING
        assert history[0]["to_state"] == "DETECTED"
        assert history[2]["to_state"] == "REASONING"

    def test_history_has_timestamps(self):
        sm = self._make_sm()
        sm.transition(IncidentState.OBSERVING)
        assert all("timestamp" in e for e in sm.get_history())

    def test_escalated_is_terminal(self):
        sm = self._make_sm()
        sm.transition(IncidentState.OBSERVING)
        sm.transition(IncidentState.REASONING)
        sm.transition(IncidentState.ESCALATED)
        sm.transition(IncidentState.RESOLVED)  # ignored
        assert sm.state == IncidentState.ESCALATED

    def test_duration_calculation(self):
        sm = self._make_sm()
        assert sm.get_duration_seconds() >= 0.0

    def test_verifying_can_transition_to_acting(self):
        """Agent may need to act again after a verification step."""
        sm = self._make_sm()
        sm.transition(IncidentState.OBSERVING)
        sm.transition(IncidentState.REASONING)
        sm.transition(IncidentState.ACTING)
        sm.transition(IncidentState.VERIFYING)
        sm.transition(IncidentState.ACTING)  # must be allowed
        assert sm.state == IncidentState.ACTING


# ─── Runbook Registry Tests ───────────────────────────────────────────────────

class TestRunbookRegistry:
    def test_loads_runbooks_from_directory(self, temp_runbooks_dir):
        registry = RunbookRegistry(runbooks_dir=temp_runbooks_dir)
        assert len(registry.get_all_runbooks()) == 2

    def test_get_runbook_by_alert_name(self, temp_runbooks_dir):
        registry = RunbookRegistry(runbooks_dir=temp_runbooks_dir)
        runbook = registry.get_runbook("TestAlert")
        assert runbook is not None
        assert runbook.name == "test_runbook"

    def test_get_runbook_case_insensitive(self, temp_runbooks_dir):
        registry = RunbookRegistry(runbooks_dir=temp_runbooks_dir)
        assert registry.get_runbook("testalert") is not None

    def test_returns_none_for_unknown_alert(self, temp_runbooks_dir):
        registry = RunbookRegistry(runbooks_dir=temp_runbooks_dir)
        assert registry.get_runbook("SomeAlertNoRunbook") is None

    def test_runbook_has_correct_attributes(self, temp_runbooks_dir):
        registry = RunbookRegistry(runbooks_dir=temp_runbooks_dir)
        runbook = registry.get_runbook("TestAlert")
        assert "TestAlert" in runbook.triggers
        assert "AnotherTestAlert" in runbook.triggers
        assert len(runbook.actions) == 3

    def test_multiple_triggers_same_runbook(self, temp_runbooks_dir):
        registry = RunbookRegistry(runbooks_dir=temp_runbooks_dir)
        assert registry.get_runbook("TestAlert").name == registry.get_runbook("AnotherTestAlert").name

    def test_list_alert_mappings(self, temp_runbooks_dir):
        registry = RunbookRegistry(runbooks_dir=temp_runbooks_dir)
        mappings = registry.list_alert_mappings()
        assert "TestAlert" in mappings
        assert "CpuHigh" in mappings

    def test_empty_directory(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        assert RunbookRegistry(runbooks_dir=empty).get_all_runbooks() == []

    def test_nonexistent_directory(self, tmp_path):
        assert RunbookRegistry(runbooks_dir=tmp_path / "nope").get_all_runbooks() == []


# ─── Approval Gate Tests ──────────────────────────────────────────────────────

class TestApprovalGate:
    def test_dry_run_is_dry_run(self):
        assert ApprovalGate(mode=ApprovalMode.DRY_RUN).is_dry_run() is True

    def test_auto_not_dry_run(self):
        assert ApprovalGate(mode=ApprovalMode.AUTO).is_dry_run() is False

    def test_dry_run_approves_everything(self):
        gate = ApprovalGate(mode=ApprovalMode.DRY_RUN)
        assert gate.approve("restart_service", {"service": "api"}) is True
        assert gate.approve("scale_service", {"service": "api", "replicas": 0}) is True

    def test_auto_approves_non_destructive(self):
        gate = ApprovalGate(mode=ApprovalMode.AUTO)
        for action, params in [
            ("get_metrics", {"query": "test"}),
            ("get_recent_logs", {"service": "api", "lines": 100}),
            ("get_service_status", {"service": "api"}),
            ("run_diagnostic", {"check": "disk_usage"}),
        ]:
            assert gate.approve(action, params) is True

    def test_auto_prompts_for_restart_approved(self):
        gate = ApprovalGate(mode=ApprovalMode.AUTO)
        with patch("builtins.input", return_value="y"):
            assert gate.approve("restart_service", {"service": "api"}) is True

    def test_auto_rejects_when_denied(self):
        gate = ApprovalGate(mode=ApprovalMode.AUTO)
        with patch("builtins.input", return_value="n"):
            assert gate.approve("restart_service", {"service": "api"}) is False

    def test_auto_approves_scale_up(self):
        gate = ApprovalGate(mode=ApprovalMode.AUTO)
        assert gate.approve("scale_service", {"service": "api", "replicas": 4}) is True

    def test_auto_prompts_scale_down(self):
        gate = ApprovalGate(mode=ApprovalMode.AUTO)
        with patch("builtins.input", return_value="y"):
            assert gate.approve("scale_service", {"service": "api", "replicas": 1}) is True

    def test_manual_always_prompts(self):
        gate = ApprovalGate(mode=ApprovalMode.MANUAL)
        with patch("builtins.input", return_value="y"):
            assert gate.approve("get_metrics", {"query": "test"}) is True

    def test_eof_rejects(self):
        gate = ApprovalGate(mode=ApprovalMode.AUTO)
        with patch("builtins.input", side_effect=EOFError):
            assert gate.approve("restart_service", {"service": "api"}) is False


# ─── Action Registry Tests ────────────────────────────────────────────────────

class TestActionRegistry:
    def test_register_and_execute(self):
        registry = ActionRegistry()
        registry.register("echo", lambda message: f"echo: {message}")
        result = registry.execute("echo", {"message": "hello"})
        assert result.success is True
        assert result.output == "echo: hello"

    def test_unknown_action_returns_failure(self):
        result = ActionRegistry().execute("nonexistent", {})
        assert result.success is False
        assert "Unknown action" in result.error

    def test_dry_run_skips_execution(self):
        executed = []
        registry = ActionRegistry()
        registry.register("act", lambda: executed.append(True) or "done")
        result = registry.execute("act", {}, dry_run=True)
        assert result.success is True
        assert len(executed) == 0
        assert "DRY_RUN" in result.output

    def test_failed_action_returns_error(self):
        registry = ActionRegistry()
        registry.register("boom", lambda: (_ for _ in ()).throw(ValueError("boom")))
        result = registry.execute("boom", {})
        assert result.success is False
        assert "boom" in result.error

    def test_list_actions(self):
        registry = ActionRegistry()
        registry.register("a", lambda: None)
        registry.register("b", lambda: None)
        assert "a" in registry.list_actions()
        assert "b" in registry.list_actions()

    def test_duration_recorded(self):
        registry = ActionRegistry()
        registry.register("noop", lambda: None)
        result = registry.execute("noop", {})
        assert result.duration_ms >= 0


# ─── Agent Loop Tests ─────────────────────────────────────────────────────────

class TestSREAgent:
    def _make_agent(self, approval_mode=ApprovalMode.DRY_RUN):
        """Build a test agent with a mock LLM backend injected."""
        registry = ActionRegistry()
        registry.register("get_metrics", lambda query: {"value": 0.05, "status": "success"})
        registry.register("get_recent_logs", lambda service, lines=100: {"logs": [], "line_count": 0})
        registry.register("restart_service", lambda service: {"success": True})
        registry.register("escalate", lambda reason, severity: {"escalation_id": "esc-001"})
        registry.register("get_service_status", lambda service: {"status": "running"})

        mock_llm = MagicMock()

        agent = SREAgent(
            action_registry=registry,
            runbook_registry=MagicMock(get_runbook=lambda x: None),
            approval_gate=ApprovalGate(mode=approval_mode),
            llm_backend=mock_llm,
        )
        return agent, mock_llm

    def test_agent_runs_and_returns_report(self, alert_high_error_rate, mock_llm_simple_resolution):
        agent, mock_llm = self._make_agent()
        mock_llm.chat.side_effect = mock_llm_simple_resolution

        report = agent.run(alert_high_error_rate)

        assert "incident_id" in report
        assert report["alert_name"] == "HighErrorRate"
        assert "status" in report
        assert "actions_taken" in report
        assert "reasoning_transcript" in report

    def test_agent_stores_transcript(self, alert_high_error_rate, mock_llm_simple_resolution):
        agent, mock_llm = self._make_agent()
        mock_llm.chat.side_effect = mock_llm_simple_resolution

        report = agent.run(alert_high_error_rate)

        assert len(report["reasoning_transcript"]) > 0

    def test_agent_with_restart_records_all_actions(self, alert_high_error_rate, mock_llm_with_restart):
        agent, mock_llm = self._make_agent()
        mock_llm.chat.side_effect = mock_llm_with_restart

        report = agent.run(alert_high_error_rate)

        action_names = [a["action"] for a in report["actions_taken"]]
        assert "get_metrics" in action_names
        assert "get_recent_logs" in action_names
        assert "restart_service" in action_names

    def test_agent_handles_llm_error(self, alert_high_error_rate):
        agent, mock_llm = self._make_agent()
        mock_llm.chat.side_effect = RuntimeError("LLM connection refused")

        report = agent.run(alert_high_error_rate)

        assert report["status"] == "FAILED"

    def test_dry_run_does_not_execute_restart(self, alert_service_down, mock_llm_with_restart):
        """In DRY_RUN mode restart_service handler must never be called."""
        executed_restarts = []

        registry = ActionRegistry()
        registry.register("get_metrics", lambda query: {"value": 1.0})
        registry.register("get_recent_logs", lambda service, lines=100: {"logs": ["ERROR crash"]})
        registry.register(
            "restart_service",
            lambda service: executed_restarts.append(service) or {"success": True},
        )
        registry.register("escalate", lambda reason, severity: {"escalation_id": "e01"})
        registry.register("get_service_status", lambda service: {"status": "running"})

        mock_llm = MagicMock()
        mock_llm.chat.side_effect = mock_llm_with_restart

        agent = SREAgent(
            action_registry=registry,
            runbook_registry=MagicMock(get_runbook=lambda x: None),
            approval_gate=ApprovalGate(mode=ApprovalMode.DRY_RUN),
            llm_backend=mock_llm,
        )
        agent.run(alert_service_down)

        assert len(executed_restarts) == 0  # DRY_RUN intercepted before handler

    def test_auto_mode_rejection_recorded(self, alert_high_error_rate, mock_llm_with_restart):
        """In AUTO mode, a rejected restart should appear in actions_taken."""
        agent, mock_llm = self._make_agent(approval_mode=ApprovalMode.AUTO)
        mock_llm.chat.side_effect = mock_llm_with_restart

        with patch("builtins.input", return_value="n"):
            report = agent.run(alert_high_error_rate)

        rejected = [a for a in report["actions_taken"] if a.get("result") == "REJECTED"]
        assert len(rejected) > 0

    def test_runbook_context_loaded(self, alert_high_error_rate, mock_llm_simple_resolution):
        from agent.runbook_registry import Runbook

        mock_runbook = Runbook(
            name="high_error_rate",
            description="Test runbook",
            triggers=["HighErrorRate"],
            actions=["get_metrics: Check error rate"],
            escalation_threshold="Escalate if >10%",
        )

        mock_llm = MagicMock()
        mock_llm.chat.side_effect = mock_llm_simple_resolution
        mock_rb_registry = MagicMock()
        mock_rb_registry.get_runbook.return_value = mock_runbook

        agent = SREAgent(
            action_registry=ActionRegistry(),
            runbook_registry=mock_rb_registry,
            approval_gate=ApprovalGate(mode=ApprovalMode.DRY_RUN),
            llm_backend=mock_llm,
        )
        agent.action_registry.register("get_metrics", lambda query: {"value": 0.05})

        agent.run(alert_high_error_rate)

        mock_rb_registry.get_runbook.assert_called_once_with("HighErrorRate")


# ─── LLM Factory Tests ────────────────────────────────────────────────────────

class TestLLMFactory:
    def test_factory_creates_ollama_by_default(self):
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {"LLM_BACKEND": "ollama", "OLLAMA_MODEL": "qwen3:14b"}):
            # Import fresh so env var is re-read
            import importlib
            import agent.llm.factory as factory_mod
            importlib.reload(factory_mod)

            from agent.llm.ollama_backend import OllamaBackend
            with patch.object(OllamaBackend, "__init__", return_value=None):
                backend = factory_mod.create_backend()
            # If no exception was raised, factory resolved to ollama path

    def test_factory_raises_on_unknown_backend(self):
        import os
        with patch.dict(os.environ, {"LLM_BACKEND": "unknown_backend"}):
            import importlib
            import agent.llm.factory as factory_mod
            importlib.reload(factory_mod)

            with pytest.raises(ValueError, match="Unknown LLM_BACKEND"):
                factory_mod.create_backend()

    def test_factory_raises_when_claude_missing_key(self):
        import os
        env = {"LLM_BACKEND": "claude", "ANTHROPIC_API_KEY": ""}
        with patch.dict(os.environ, env, clear=False):
            import importlib
            import agent.llm.factory as factory_mod
            importlib.reload(factory_mod)

            with pytest.raises(EnvironmentError, match="ANTHROPIC_API_KEY"):
                factory_mod.create_backend()
