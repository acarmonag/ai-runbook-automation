"""
Tests for LLM backend message format conversion.

Covers the Anthropic ↔ OpenAI message translation in OllamaBackend,
and the response normalization in both backends.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from agent.llm.base import LLMResponse, ToolCall


# ─── OllamaBackend message conversion ────────────────────────────────────────

class TestOllamaMessageConversion:
    def _backend(self):
        from agent.llm.ollama_backend import OllamaBackend
        with patch("agent.llm.ollama_backend.OpenAI"):
            b = OllamaBackend(model="qwen3:14b", base_url="http://localhost:11434")
        return b

    def test_plain_string_message_passes_through(self):
        b = self._backend()
        messages = [{"role": "user", "content": "hello"}]
        result = b._convert_messages_to_oai(messages)
        assert result == [{"role": "user", "content": "hello"}]

    def test_assistant_text_block_converted(self):
        b = self._backend()
        messages = [{"role": "assistant", "content": [
            {"type": "text", "text": "I will check metrics."}
        ]}]
        result = b._convert_messages_to_oai(messages)
        assert len(result) == 1
        assert result[0]["role"] == "assistant"
        assert result[0]["content"] == "I will check metrics."

    def test_assistant_tool_use_block_converted(self):
        b = self._backend()
        messages = [{"role": "assistant", "content": [
            {"type": "text", "text": "Checking metrics."},
            {"type": "tool_use", "id": "t001", "name": "get_metrics",
             "input": {"query": "rate(errors[5m])"}},
        ]}]
        result = b._convert_messages_to_oai(messages)
        assert len(result) == 1
        msg = result[0]
        assert msg["role"] == "assistant"
        assert len(msg["tool_calls"]) == 1
        tc = msg["tool_calls"][0]
        assert tc["id"] == "t001"
        assert tc["function"]["name"] == "get_metrics"
        assert json.loads(tc["function"]["arguments"]) == {"query": "rate(errors[5m])"}

    def test_tool_result_blocks_become_tool_messages(self):
        b = self._backend()
        messages = [{"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t001",
             "content": '{"value": 0.15, "status": "success"}'},
        ]}]
        result = b._convert_messages_to_oai(messages)
        assert len(result) == 1
        assert result[0]["role"] == "tool"
        assert result[0]["tool_call_id"] == "t001"
        assert "0.15" in result[0]["content"]

    def test_multiple_tool_results_become_separate_messages(self):
        b = self._backend()
        messages = [{"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t001", "content": "result1"},
            {"type": "tool_result", "tool_use_id": "t002", "content": "result2"},
        ]}]
        result = b._convert_messages_to_oai(messages)
        assert len(result) == 2
        assert result[0]["tool_call_id"] == "t001"
        assert result[1]["tool_call_id"] == "t002"

    def test_tool_definition_conversion(self):
        b = self._backend()
        tools = [{
            "name": "get_metrics",
            "description": "Run a PromQL query",
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        }]
        result = b._convert_tools_to_oai(tools)
        assert len(result) == 1
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "get_metrics"
        assert result[0]["function"]["parameters"]["required"] == ["query"]

    def test_full_conversation_roundtrip(self):
        """A multi-turn conversation with tool calls converts without loss."""
        b = self._backend()
        messages = [
            {"role": "user", "content": "Investigate high error rate"},
            {"role": "assistant", "content": [
                {"type": "text", "text": "I'll check metrics."},
                {"type": "tool_use", "id": "t001", "name": "get_metrics",
                 "input": {"query": "rate(errors[5m])"}},
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "t001", "content": '{"value": 0.15}'},
            ]},
            {"role": "assistant", "content": [
                {"type": "text", "text": "High error rate confirmed."},
            ]},
        ]
        result = b._convert_messages_to_oai(messages)
        # user → user, assistant+tool → assistant+tool_calls, tool_result → tool, assistant text → assistant
        roles = [m["role"] for m in result]
        assert "user" in roles
        assert "assistant" in roles
        assert "tool" in roles


# ─── OllamaBackend response parsing ──────────────────────────────────────────

class TestOllamaResponseParsing:
    def _backend(self):
        from agent.llm.ollama_backend import OllamaBackend
        with patch("agent.llm.ollama_backend.OpenAI"):
            b = OllamaBackend(model="qwen3:14b", base_url="http://localhost:11434")
        return b

    def _make_oai_response(self, content=None, tool_calls=None, finish_reason="stop"):
        choice = MagicMock()
        choice.finish_reason = finish_reason
        choice.message.content = content
        choice.message.tool_calls = tool_calls or []
        response = MagicMock()
        response.choices = [choice]
        return response

    def test_text_response_parsed(self):
        b = self._backend()
        resp = self._make_oai_response(content="Here is my analysis.", finish_reason="stop")
        result = b._parse_oai_response(resp)

        assert result.stop_reason == "end_turn"
        assert result.text == "Here is my analysis."
        assert result.tool_calls == []

    def test_tool_call_response_parsed(self):
        b = self._backend()
        tc = MagicMock()
        tc.id = "call_001"
        tc.function.name = "get_metrics"
        tc.function.arguments = '{"query": "rate(errors[5m])"}'

        resp = self._make_oai_response(content=None, tool_calls=[tc], finish_reason="tool_calls")
        result = b._parse_oai_response(resp)

        assert result.stop_reason == "tool_use"
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "get_metrics"
        assert result.tool_calls[0].input == {"query": "rate(errors[5m])"}
        assert result.tool_calls[0].id == "call_001"

    def test_malformed_tool_args_fall_back_to_empty(self):
        b = self._backend()
        tc = MagicMock()
        tc.id = "call_bad"
        tc.function.name = "restart_service"
        tc.function.arguments = "NOT VALID JSON {{{"

        resp = self._make_oai_response(content=None, tool_calls=[tc])
        result = b._parse_oai_response(resp)  # should not raise

        assert result.tool_calls[0].input == {}

    def test_raw_assistant_message_in_anthropic_format(self):
        """raw_assistant_message must be in Anthropic format for history storage."""
        b = self._backend()
        tc = MagicMock()
        tc.id = "call_001"
        tc.function.name = "get_metrics"
        tc.function.arguments = '{"query": "cpu"}'

        resp = self._make_oai_response(content="Checking.", tool_calls=[tc])
        result = b._parse_oai_response(resp)

        raw = result.raw_assistant_message
        assert raw["role"] == "assistant"
        content_types = [b["type"] for b in raw["content"]]
        assert "text" in content_types
        assert "tool_use" in content_types

    def test_multiple_tool_calls_parsed(self):
        b = self._backend()
        tcs = []
        for i, name in enumerate(["get_metrics", "get_recent_logs"]):
            tc = MagicMock()
            tc.id = f"call_{i:03}"
            tc.function.name = name
            tc.function.arguments = '{"query": "x"}' if name == "get_metrics" else '{"service": "api"}'
            tcs.append(tc)

        resp = self._make_oai_response(tool_calls=tcs)
        result = b._parse_oai_response(resp)

        assert len(result.tool_calls) == 2
        assert result.tool_calls[0].name == "get_metrics"
        assert result.tool_calls[1].name == "get_recent_logs"


# ─── ClaudeBackend tests ──────────────────────────────────────────────────────

class TestClaudeBackend:
    def _make_block(self, btype, **kwargs):
        block = MagicMock()
        block.type = btype
        for k, v in kwargs.items():
            setattr(block, k, v)
        return block

    def _make_anthropic_response(self, blocks, stop_reason="tool_use"):
        response = MagicMock()
        response.content = blocks
        response.stop_reason = stop_reason
        return response

    def test_text_response_normalized(self):
        from agent.llm.claude_backend import ClaudeBackend
        with patch("agent.llm.claude_backend.anthropic.Anthropic"):
            backend = ClaudeBackend()

        response = self._make_anthropic_response(
            [self._make_block("text", text="Analysis complete.")],
            stop_reason="end_turn",
        )
        with patch.object(backend.client.messages, "create", return_value=response):
            result = backend.chat("sys", [], [])

        assert result.stop_reason == "end_turn"
        assert result.text == "Analysis complete."
        assert result.tool_calls == []

    def test_tool_use_response_normalized(self):
        from agent.llm.claude_backend import ClaudeBackend
        with patch("agent.llm.claude_backend.anthropic.Anthropic"):
            backend = ClaudeBackend()

        response = self._make_anthropic_response(
            [
                self._make_block("text", text="Checking."),
                self._make_block("tool_use", id="t001", name="get_metrics",
                                 input={"query": "rate(errors[5m])"}),
            ],
            stop_reason="tool_use",
        )
        with patch.object(backend.client.messages, "create", return_value=response):
            result = backend.chat("sys", [], [])

        assert result.stop_reason == "tool_use"
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "get_metrics"

    def test_raw_message_in_anthropic_format(self):
        from agent.llm.claude_backend import ClaudeBackend
        with patch("agent.llm.claude_backend.anthropic.Anthropic"):
            backend = ClaudeBackend()

        response = self._make_anthropic_response(
            [self._make_block("tool_use", id="t001", name="restart_service",
                              input={"service": "api"})],
        )
        with patch.object(backend.client.messages, "create", return_value=response):
            result = backend.chat("sys", [], [])

        raw = result.raw_assistant_message
        assert raw["role"] == "assistant"
        assert any(b["type"] == "tool_use" for b in raw["content"])
