from __future__ import annotations

"""
Log collection actions — read container logs and parse error patterns.

Falls back to mock log endpoint when Docker container is not accessible.
"""

import logging
import os
import re
from collections import Counter
from typing import Any

import httpx

from agent.actions.service_resolver import resolve_or_original

logger = logging.getLogger(__name__)

MAX_LINES = 500
PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://localhost:9091")
USE_MOCK_LOGS = os.environ.get("USE_MOCK_LOGS", "false").lower() == "true"

ERROR_PATTERNS = [
    (re.compile(r"\bERROR\b", re.IGNORECASE), "ERROR"),
    (re.compile(r"\bCRITICAL\b", re.IGNORECASE), "CRITICAL"),
    (re.compile(r"\bFATAL\b", re.IGNORECASE), "FATAL"),
    (re.compile(r"\bPANIC\b", re.IGNORECASE), "PANIC"),
    (re.compile(r"exception", re.IGNORECASE), "EXCEPTION"),
    (re.compile(r"traceback", re.IGNORECASE), "TRACEBACK"),
    (re.compile(r"out of memory", re.IGNORECASE), "OOM"),
    (re.compile(r"connection refused", re.IGNORECASE), "CONN_REFUSED"),
    (re.compile(r"timeout", re.IGNORECASE), "TIMEOUT"),
    (re.compile(r"segmentation fault", re.IGNORECASE), "SEGFAULT"),
]


def get_recent_logs(service: str, lines: int = 100) -> dict[str, Any]:
    """
    Fetch the most recent log lines from a Docker container.

    Falls back to mock logs endpoint if Docker is unavailable or
    USE_MOCK_LOGS=true is set.

    Returns: raw_logs, line_count, error_count, sample_errors
    """
    lines = min(lines, MAX_LINES)
    logger.debug(f"Fetching {lines} log lines from service: {service}")

    # Try Docker first (unless mock-only mode)
    if not USE_MOCK_LOGS:
        docker_result = _get_docker_logs(service, lines)
        if docker_result is not None:
            return docker_result
        logger.info(f"Docker logs unavailable for '{service}', falling back to mock logs")

    # Fall back to mock logs endpoint
    return _get_mock_logs(service, lines)


def _get_docker_logs(service: str, lines: int) -> dict[str, Any] | None:
    """
    Attempt to fetch logs from Docker. Returns None on failure (triggers fallback).
    """
    try:
        import docker
        client = docker.from_env()
    except ImportError:
        return None
    except Exception:
        return None

    try:
        resolved = resolve_or_original(service, client)
        containers = client.containers.list(all=True, filters={"name": resolved})
        if not containers:
            return None

        container = containers[0]
        raw = container.logs(tail=lines, timestamps=True).decode("utf-8", errors="replace")
        log_lines = [l for l in raw.splitlines() if l.strip()]

        parsed = parse_error_patterns(log_lines)

        return {
            "service": service,
            "container_name": container.name,
            "container_id": container.short_id,
            "source": "docker",
            "line_count": len(log_lines),
            "logs": log_lines[-50:],
            "error_summary": parsed,
            "has_errors": parsed["total_error_lines"] > 0,
        }

    except Exception as e:
        logger.debug(f"Docker log fetch failed for '{service}': {e}")
        return None


def _get_mock_logs(service: str, lines: int) -> dict[str, Any]:
    """
    Fetch synthetic logs from the mock Prometheus logs endpoint.
    """
    try:
        resp = httpx.get(
            f"{PROMETHEUS_URL}/api/v1/logs",
            params={"service": service, "lines": lines},
            timeout=5.0,
        )
        resp.raise_for_status()
        data = resp.json()
        log_lines = data.get("logs", [])
        parsed = parse_error_patterns(log_lines)

        return {
            "service": service,
            "source": "mock",
            "scenario": data.get("scenario", "unknown"),
            "phase": data.get("phase", "unknown"),
            "line_count": len(log_lines),
            "logs": log_lines,
            "error_summary": parsed,
            "has_errors": parsed["total_error_lines"] > 0,
        }
    except Exception as e:
        logger.error(f"Mock log fetch failed for '{service}': {e}")
        return {
            "service": service,
            "source": "mock",
            "error": f"Could not retrieve logs: {e}",
            "logs": [],
            "line_count": 0,
            "error_summary": {"total_error_lines": 0, "pattern_counts": {}, "sample_error_lines": [], "error_types": [], "sample_by_type": {}},
            "has_errors": False,
        }


def parse_error_patterns(logs: list[str]) -> dict[str, Any]:
    """
    Parse log lines and extract error patterns with counts.
    """
    error_lines = []
    pattern_counts: Counter = Counter()
    sample_messages: dict[str, list[str]] = {}

    for line in logs:
        matched_any = False
        for pattern, label in ERROR_PATTERNS:
            if pattern.search(line):
                pattern_counts[label] += 1
                matched_any = True
                if label not in sample_messages:
                    sample_messages[label] = []
                if len(sample_messages[label]) < 3:
                    sample_messages[label].append(line[:200])

        if matched_any:
            error_lines.append(line[:200])

    return {
        "total_error_lines": len(error_lines),
        "pattern_counts": dict(pattern_counts),
        "sample_error_lines": error_lines[:10],
        "error_types": list(pattern_counts.keys()),
        "sample_by_type": sample_messages,
    }
