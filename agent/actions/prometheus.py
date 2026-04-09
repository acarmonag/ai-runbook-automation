"""
Prometheus action — runs PromQL queries against the configured Prometheus instance.
"""

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://localhost:9091")
REQUEST_TIMEOUT = 10.0


def get_metrics(query: str) -> dict[str, Any]:
    """
    Run a PromQL instant query against Prometheus.

    Returns:
        dict with keys: value, timestamp, labels, raw_result
    """
    url = f"{PROMETHEUS_URL}/api/v1/query"
    params = {"query": query}

    logger.debug(f"Prometheus query: {query}")

    try:
        response = httpx.get(url, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
    except httpx.ConnectError as e:
        logger.error(f"Cannot connect to Prometheus at {PROMETHEUS_URL}: {e}")
        return {
            "error": f"Cannot connect to Prometheus: {e}",
            "query": query,
            "status": "connection_error",
        }
    except httpx.TimeoutException:
        logger.error(f"Prometheus query timed out: {query}")
        return {
            "error": "Prometheus query timed out",
            "query": query,
            "status": "timeout",
        }
    except httpx.HTTPStatusError as e:
        logger.error(f"Prometheus returned error {e.response.status_code}: {e}")
        return {
            "error": f"Prometheus HTTP error: {e.response.status_code}",
            "query": query,
            "status": "http_error",
        }

    if data.get("status") != "success":
        return {
            "error": data.get("error", "Unknown Prometheus error"),
            "query": query,
            "status": "query_error",
        }

    result_type = data.get("data", {}).get("resultType", "unknown")
    results = data.get("data", {}).get("result", [])

    if not results:
        return {
            "query": query,
            "result_type": result_type,
            "value": None,
            "values": [],
            "message": "No data returned for query",
            "status": "no_data",
        }

    # For instant queries, return the first result with labels
    first = results[0]
    metric_labels = first.get("metric", {})
    raw_value = first.get("value", [None, None])

    timestamp = raw_value[0] if raw_value[0] else None
    value = raw_value[1] if raw_value[1] else None

    # Try to convert value to float
    try:
        value = float(value) if value is not None else None
    except (ValueError, TypeError):
        pass

    return {
        "query": query,
        "result_type": result_type,
        "value": value,
        "timestamp": timestamp,
        "labels": metric_labels,
        "all_results": [
            {
                "labels": r.get("metric", {}),
                "value": r.get("value", [None, None])[1],
            }
            for r in results
        ],
        "status": "success",
    }
