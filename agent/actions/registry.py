from __future__ import annotations

"""
Action registry — maps action names to handler functions and executes them.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class ActionResult:
    success: bool
    output: Any = None
    duration_ms: int = 0
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "output": self.output,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


class ActionRegistry:
    def __init__(self):
        self._handlers: dict[str, Callable] = {}

    def register(self, name: str, handler: Callable) -> None:
        """Register an action handler by name."""
        self._handlers[name] = handler
        logger.debug(f"Registered action: {name}")

    def execute(
        self,
        action_name: str,
        params: dict[str, Any],
        dry_run: bool = False,
    ) -> ActionResult:
        """
        Execute a registered action with the given parameters.

        If dry_run=True, log the action but don't execute it.
        Returns an ActionResult with success/failure details.
        """
        handler = self._handlers.get(action_name)
        if not handler:
            return ActionResult(
                success=False,
                error=f"Unknown action: {action_name}",
            )

        if dry_run:
            logger.info(f"DRY_RUN: Would execute {action_name}({params})")
            return ActionResult(
                success=True,
                output=f"[DRY_RUN] {action_name} would have been executed with params: {params}",
            )

        start = time.time()
        try:
            output = handler(**params)
            duration_ms = int((time.time() - start) * 1000)
            logger.info(f"Action {action_name} completed in {duration_ms}ms")
            return ActionResult(success=True, output=output, duration_ms=duration_ms)
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            logger.error(f"Action {action_name} failed: {e}")
            return ActionResult(
                success=False,
                output=None,
                duration_ms=duration_ms,
                error=str(e),
            )

    def list_actions(self) -> list[str]:
        """Return all registered action names."""
        return list(self._handlers.keys())


def build_default_registry() -> ActionRegistry:
    """Build and return the default action registry with all handlers registered."""
    from agent.actions.prometheus import get_metrics
    from agent.actions.docker_actions import (
        scale_service,
        restart_service,
        get_service_status,
    )
    from agent.actions.log_actions import get_recent_logs
    from agent.actions.diagnostic import run_diagnostic
    from agent.actions.escalation import escalate

    registry = ActionRegistry()
    registry.register("get_metrics", get_metrics)
    registry.register("get_recent_logs", get_recent_logs)
    registry.register("get_service_status", get_service_status)
    registry.register("scale_service", scale_service)
    registry.register("restart_service", restart_service)
    registry.register("run_diagnostic", run_diagnostic)
    registry.register("escalate", escalate)

    return registry
