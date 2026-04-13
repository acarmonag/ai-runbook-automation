from __future__ import annotations

"""
Runbook registry — loads runbook definitions from YAML files
and maps alert names to runbooks.
"""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class Runbook:
    name: str
    description: str
    triggers: list[str]
    actions: list[str]
    escalation_threshold: str = ""
    metadata: dict = field(default_factory=dict)
    verification: dict = field(default_factory=dict)


class RunbookRegistry:
    def __init__(self, runbooks_dir: str | Path = "runbooks"):
        self.runbooks_dir = Path(runbooks_dir)
        self._runbooks: dict[str, Runbook] = {}
        self._alert_map: dict[str, str] = {}  # alert_name → runbook_name
        self._load_runbooks()

    def _load_runbooks(self) -> None:
        """Load all YAML runbook definitions from the runbooks directory."""
        if not self.runbooks_dir.exists():
            logger.warning(f"Runbooks directory not found: {self.runbooks_dir}")
            return

        for yml_file in self.runbooks_dir.glob("*.yml"):
            try:
                self._load_runbook_file(yml_file)
            except Exception as e:
                logger.error(f"Failed to load runbook {yml_file}: {e}")

        logger.info(
            f"Loaded {len(self._runbooks)} runbooks covering "
            f"{len(self._alert_map)} alert triggers"
        )

    def _load_runbook_file(self, path: Path) -> None:
        """Parse a single YAML runbook file."""
        with open(path) as f:
            data = yaml.safe_load(f)

        if not data:
            logger.warning(f"Empty runbook file: {path}")
            return

        runbook = Runbook(
            name=data.get("name", path.stem),
            description=data.get("description", ""),
            triggers=data.get("triggers", []),
            actions=data.get("actions", []),
            escalation_threshold=data.get("escalation_threshold", ""),
            metadata=data.get("metadata", {}),
            verification=data.get("verification", {}),
        )

        self._runbooks[runbook.name] = runbook

        for alert_name in runbook.triggers:
            if alert_name in self._alert_map:
                logger.warning(
                    f"Alert '{alert_name}' already mapped to '{self._alert_map[alert_name]}', "
                    f"overwriting with '{runbook.name}'"
                )
            self._alert_map[alert_name] = runbook.name
            logger.debug(f"Mapped alert '{alert_name}' → runbook '{runbook.name}'")

    def get_runbook(self, alert_name: str) -> Optional[Runbook]:
        """Look up a runbook by alert name."""
        runbook_name = self._alert_map.get(alert_name)
        if not runbook_name:
            # Try case-insensitive match
            for key, val in self._alert_map.items():
                if key.lower() == alert_name.lower():
                    runbook_name = val
                    break
        if not runbook_name:
            return None
        return self._runbooks.get(runbook_name)

    def get_all_runbooks(self) -> list[Runbook]:
        """Return all loaded runbooks."""
        return list(self._runbooks.values())

    def list_alert_mappings(self) -> dict[str, str]:
        """Return all alert → runbook mappings."""
        return dict(self._alert_map)
