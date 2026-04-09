"""
Claude API backend — uses the Anthropic SDK.

Requires: ANTHROPIC_API_KEY environment variable.
"""

import logging
import os

import anthropic

from agent.llm.base import LLMResponse, ToolCall

logger = logging.getLogger(__name__)


class ClaudeBackend:
    """LLM backend that calls the Anthropic Claude API."""

    def __init__(self, model: str = "claude-sonnet-4-5"):
        self.model = model
        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        logger.info(f"ClaudeBackend initialized — model: {self.model}")

    def chat(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
    ) -> LLMResponse:
        """Send a chat request to Claude and return a normalized LLMResponse."""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system,
            tools=tools,
            messages=messages,
        )

        text = None
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                text = block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    input=block.input,
                ))

        # Build Anthropic-format history entry from the raw SDK objects
        raw_content = []
        for block in response.content:
            if block.type == "text":
                raw_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                raw_content.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

        return LLMResponse(
            stop_reason=response.stop_reason,
            tool_calls=tool_calls,
            text=text,
            raw_assistant_message={"role": "assistant", "content": raw_content},
        )
