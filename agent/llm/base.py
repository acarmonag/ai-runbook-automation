from __future__ import annotations

"""
Shared types for the LLM abstraction layer.

Both backends (Claude, Ollama) return LLMResponse so agent.py
stays completely backend-agnostic.
"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class LLMResponse:
    stop_reason: str                  # "end_turn" | "tool_use"
    tool_calls: list[ToolCall] = field(default_factory=list)
    text: Optional[str] = None
    # Stored in Anthropic-format so the message history stays consistent
    # regardless of which backend produced the response.
    raw_assistant_message: dict = field(default_factory=dict)
