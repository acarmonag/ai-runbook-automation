"""
Diagnostic actions — predefined system health checks.
"""

import logging
import os
import shutil
from typing import Any

import httpx

logger = logging.getLogger(__name__)

PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://localhost:9091")


def run_diagnostic(check: str) -> dict[str, Any]:
    """
    Run a predefined diagnostic check.

    Available checks:
    - disk_usage: Check disk usage percentage
    - memory_pressure: Check available memory
    - connection_count: Check open connections
    - error_rate: Query Prometheus for current error rate
    """
    dispatch = {
        "disk_usage": _check_disk_usage,
        "memory_pressure": _check_memory_pressure,
        "connection_count": _check_connection_count,
        "error_rate": _check_error_rate,
    }

    handler = dispatch.get(check)
    if not handler:
        return {
            "check": check,
            "error": f"Unknown diagnostic check: '{check}'. Available: {list(dispatch)}",
            "status": "error",
        }

    try:
        return handler()
    except Exception as e:
        logger.error(f"Diagnostic '{check}' failed: {e}")
        return {"check": check, "error": str(e), "status": "error"}


def _check_disk_usage() -> dict[str, Any]:
    """Check disk usage for the root filesystem."""
    try:
        total, used, free = shutil.disk_usage("/")
        used_pct = (used / total) * 100
        return {
            "check": "disk_usage",
            "status": "ok" if used_pct < 85 else "warning" if used_pct < 95 else "critical",
            "used_percent": round(used_pct, 2),
            "total_gb": round(total / 1e9, 2),
            "used_gb": round(used / 1e9, 2),
            "free_gb": round(free / 1e9, 2),
            "threshold_warning": 85.0,
            "threshold_critical": 95.0,
        }
    except OSError as e:
        return {"check": "disk_usage", "error": str(e), "status": "error"}


def _check_memory_pressure() -> dict[str, Any]:
    """Check system memory availability."""
    try:
        import psutil

        vm = psutil.virtual_memory()
        used_pct = vm.percent
        return {
            "check": "memory_pressure",
            "status": "ok" if used_pct < 80 else "warning" if used_pct < 90 else "critical",
            "used_percent": round(used_pct, 2),
            "total_mb": round(vm.total / 1e6, 2),
            "available_mb": round(vm.available / 1e6, 2),
            "used_mb": round(vm.used / 1e6, 2),
            "threshold_warning": 80.0,
            "threshold_critical": 90.0,
        }
    except ImportError:
        # Fallback to /proc/meminfo if psutil not available
        return _read_proc_meminfo()
    except Exception as e:
        return {"check": "memory_pressure", "error": str(e), "status": "error"}


def _read_proc_meminfo() -> dict[str, Any]:
    """Read memory info from /proc/meminfo as fallback."""
    try:
        with open("/proc/meminfo") as f:
            lines = f.readlines()
        mem_info = {}
        for line in lines:
            parts = line.split()
            if len(parts) >= 2:
                key = parts[0].rstrip(":")
                try:
                    mem_info[key] = int(parts[1])
                except ValueError:
                    pass

        total_kb = mem_info.get("MemTotal", 0)
        available_kb = mem_info.get("MemAvailable", mem_info.get("MemFree", 0))
        used_kb = total_kb - available_kb
        used_pct = (used_kb / total_kb * 100) if total_kb > 0 else 0

        return {
            "check": "memory_pressure",
            "status": "ok" if used_pct < 80 else "warning" if used_pct < 90 else "critical",
            "used_percent": round(used_pct, 2),
            "total_mb": round(total_kb / 1024, 2),
            "available_mb": round(available_kb / 1024, 2),
        }
    except OSError:
        return {
            "check": "memory_pressure",
            "status": "unknown",
            "message": "Cannot read memory info (not Linux or psutil not installed)",
        }


def _check_connection_count() -> dict[str, Any]:
    """Check number of open network connections."""
    try:
        import psutil

        connections = psutil.net_connections(kind="inet")
        established = [c for c in connections if c.status == "ESTABLISHED"]
        time_wait = [c for c in connections if c.status == "TIME_WAIT"]
        total = len(connections)

        return {
            "check": "connection_count",
            "status": "ok" if total < 1000 else "warning" if total < 5000 else "critical",
            "total_connections": total,
            "established": len(established),
            "time_wait": len(time_wait),
            "threshold_warning": 1000,
            "threshold_critical": 5000,
        }
    except ImportError:
        return {
            "check": "connection_count",
            "status": "unknown",
            "message": "psutil not installed — cannot count connections",
        }
    except Exception as e:
        return {"check": "connection_count", "error": str(e), "status": "error"}


def _check_error_rate() -> dict[str, Any]:
    """Query Prometheus for current HTTP error rate."""
    query = 'sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m])) * 100'
    try:
        response = httpx.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": query},
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()

        results = data.get("data", {}).get("result", [])
        if not results:
            return {
                "check": "error_rate",
                "status": "no_data",
                "error_rate_percent": None,
                "message": "No error rate data in Prometheus",
            }

        value = float(results[0].get("value", [0, "0"])[1])
        return {
            "check": "error_rate",
            "status": "ok" if value < 1 else "warning" if value < 5 else "critical",
            "error_rate_percent": round(value, 4),
            "threshold_warning": 1.0,
            "threshold_critical": 5.0,
        }

    except httpx.ConnectError:
        return {
            "check": "error_rate",
            "status": "error",
            "error": f"Cannot connect to Prometheus at {PROMETHEUS_URL}",
        }
    except Exception as e:
        return {"check": "error_rate", "error": str(e), "status": "error"}
