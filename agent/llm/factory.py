"""
LLM backend factory.

Reads LLM_BACKEND from environment and returns the appropriate backend.

  LLM_BACKEND=ollama   → OllamaBackend  (default, free, local)
  LLM_BACKEND=claude   → ClaudeBackend  (Anthropic API, requires key)
"""

import logging
import os

from agent.llm.base import LLMResponse, ToolCall  # re-export for convenience

logger = logging.getLogger(__name__)

LLM_BACKEND  = os.environ.get("LLM_BACKEND", "ollama")
OLLAMA_URL   = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:14b")


def create_backend():
    """
    Factory — returns a ready-to-use LLM backend based on env config.

    Backends are imported lazily so you don't need the anthropic package
    installed when running with Ollama, and vice versa.
    """
    backend = LLM_BACKEND.lower()

    if backend == "claude":
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise EnvironmentError(
                "LLM_BACKEND=claude requires ANTHROPIC_API_KEY to be set."
            )
        from agent.llm.claude_backend import ClaudeBackend
        logger.info("LLM backend: Claude (Anthropic API)")
        return ClaudeBackend()

    if backend == "ollama":
        from agent.llm.ollama_backend import OllamaBackend
        logger.info(f"LLM backend: Ollama ({OLLAMA_MODEL} @ {OLLAMA_URL})")
        return OllamaBackend(model=OLLAMA_MODEL, base_url=OLLAMA_URL)

    raise ValueError(
        f"Unknown LLM_BACKEND='{LLM_BACKEND}'. Valid options: ollama, claude"
    )
