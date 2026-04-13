from __future__ import annotations

"""
Ollama backend — uses the OpenAI-compatible API served by Ollama.

No API key required. Tested with qwen3:14b and qwen3:8b.

Requires: a running Ollama instance at OLLAMA_URL with the model already pulled.
  ollama pull qwen3:14b   # local machine (already installed per user)
  ollama pull qwen3:8b    # lighter model for Docker
"""

import json
import logging
from typing import Any

from openai import OpenAI

from agent.llm.base import LLMResponse, ToolCall

logger = logging.getLogger(__name__)


class OllamaBackend:
    """LLM backend that calls a locally running Ollama instance."""

    def __init__(self, model: str, base_url: str = "http://localhost:11434"):
        self.model = model
        # Ollama's OpenAI-compatible endpoint lives at /v1
        self.client = OpenAI(
            base_url=f"{base_url.rstrip('/')}/v1",
            api_key="ollama",  # Ollama ignores the key; OpenAI SDK requires one
        )
        logger.info(f"OllamaBackend initialized — model: {self.model} @ {base_url}")

    def chat(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
    ) -> LLMResponse:
        """Send a chat request to Ollama and return a normalized LLMResponse."""
        oai_messages = [{"role": "system", "content": system}]
        oai_messages.extend(self._convert_messages_to_oai(messages))
        oai_tools = self._convert_tools_to_oai(tools)

        logger.debug(f"Ollama request: {len(oai_messages)} messages, {len(oai_tools)} tools")

        response = self.client.chat.completions.create(
            model=self.model,
            messages=oai_messages,
            tools=oai_tools if oai_tools else None,
            max_tokens=4096,
        )

        return self._parse_oai_response(response)

    # ─── Message format conversion ────────────────────────────────────────────

    def _convert_messages_to_oai(self, messages: list[dict]) -> list[dict]:
        """
        Convert Anthropic-format message history to OpenAI format.

        Anthropic stores tool results as:
            {"role": "user", "content": [{"type": "tool_result", ...}]}

        OpenAI expects:
            {"role": "tool", "tool_call_id": ..., "content": ...}

        Assistant messages with tool calls also differ in structure.
        """
        result = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            if isinstance(content, str):
                result.append({"role": role, "content": content})
                continue

            if not isinstance(content, list):
                result.append({"role": role, "content": str(content)})
                continue

            text_parts: list[str] = []
            tool_calls_oai: list[dict] = []
            tool_results_oai: list[dict] = []

            for block in content:
                btype = _block_attr(block, "type")

                if btype == "text":
                    text_parts.append(_block_attr(block, "text") or "")

                elif btype == "tool_use":
                    tool_calls_oai.append({
                        "id": _block_attr(block, "id"),
                        "type": "function",
                        "function": {
                            "name": _block_attr(block, "name"),
                            "arguments": json.dumps(_block_attr(block, "input") or {}),
                        },
                    })

                elif btype == "tool_result":
                    tc_content = _block_attr(block, "content")
                    tool_results_oai.append({
                        "role": "tool",
                        "tool_call_id": _block_attr(block, "tool_use_id"),
                        "content": (
                            tc_content
                            if isinstance(tc_content, str)
                            else json.dumps(tc_content)
                        ),
                    })

            if tool_results_oai:
                # Tool result blocks become individual tool messages
                result.extend(tool_results_oai)
            elif tool_calls_oai:
                result.append({
                    "role": "assistant",
                    "content": " ".join(text_parts) if text_parts else None,
                    "tool_calls": tool_calls_oai,
                })
            elif text_parts:
                result.append({"role": role, "content": " ".join(text_parts)})

        return result

    def _convert_tools_to_oai(self, tools: list[dict]) -> list[dict]:
        """Convert Anthropic tool definitions to OpenAI function format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["input_schema"],
                },
            }
            for t in tools
        ]

    # ─── Response parsing ─────────────────────────────────────────────────────

    def _parse_oai_response(self, response: Any) -> LLMResponse:
        """Convert an OpenAI-format response to a normalized LLMResponse."""
        choice = response.choices[0]
        message = choice.message

        text: str | None = message.content
        tool_calls: list[ToolCall] = []

        if message.tool_calls:
            for tc in message.tool_calls:
                try:
                    parsed_input = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, TypeError):
                    logger.warning(
                        f"Could not parse tool arguments for {tc.function.name}: "
                        f"{tc.function.arguments!r} — using empty dict"
                    )
                    parsed_input = {}

                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    input=parsed_input,
                ))

        stop_reason = "tool_use" if tool_calls else "end_turn"

        # Build raw_assistant_message in Anthropic format so agent.py can
        # append it to the message history without knowing which backend ran.
        raw_content: list[dict] = []
        if text:
            raw_content.append({"type": "text", "text": text})
        for tc in tool_calls:
            raw_content.append({
                "type": "tool_use",
                "id": tc.id,
                "name": tc.name,
                "input": tc.input,
            })

        return LLMResponse(
            stop_reason=stop_reason,
            tool_calls=tool_calls,
            text=text,
            raw_assistant_message={
                "role": "assistant",
                "content": raw_content if raw_content else (text or ""),
            },
        )


def _block_attr(block: Any, attr: str) -> Any:
    """Get an attribute from either a dict block or an SDK object."""
    if isinstance(block, dict):
        return block.get(attr)
    return getattr(block, attr, None)
