"""
Log collection actions — read container logs and parse error patterns.
"""

import logging
import re
from collections import Counter
from typing import Any

logger = logging.getLogger(__name__)

MAX_LINES = 500

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

    Returns: raw_logs, line_count, error_count, sample_errors
    """
    lines = min(lines, MAX_LINES)
    logger.debug(f"Fetching {lines} log lines from service: {service}")

    try:
        import docker
        client = docker.from_env()
    except ImportError:
        return {"service": service, "error": "Docker SDK not installed", "logs": []}
    except Exception as e:
        return {"service": service, "error": f"Cannot connect to Docker: {e}", "logs": []}

    try:
        containers = client.containers.list(all=True, filters={"name": service})
        if not containers:
            return {
                "service": service,
                "error": f"No container found with name '{service}'",
                "logs": [],
            }

        container = containers[0]
        raw = container.logs(tail=lines, timestamps=True).decode("utf-8", errors="replace")
        log_lines = [l for l in raw.splitlines() if l.strip()]

        parsed = parse_error_patterns(log_lines)

        return {
            "service": service,
            "container_id": container.short_id,
            "line_count": len(log_lines),
            "logs": log_lines[-50:],  # Return last 50 lines to keep response manageable
            "error_summary": parsed,
            "has_errors": parsed["total_error_lines"] > 0,
        }

    except Exception as e:
        logger.error(f"Failed to get logs for service '{service}': {e}")
        return {"service": service, "error": str(e), "logs": []}


def parse_error_patterns(logs: list[str]) -> dict[str, Any]:
    """
    Parse log lines and extract error patterns with counts.

    Returns a summary of error types found.
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
                    # Truncate long lines
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
