from __future__ import annotations

"""
SRE Interpreter — enriches raw tool results with domain knowledge.

Sits between ActionRegistry.execute() and the tool_result message sent to the LLM.
Adds an `sre_insight` key to each result dict so the model receives interpreted
data rather than raw numbers it must reason about unaided.

Example transformation for get_metrics:
  Before: {"value": 0.089, "query": "rate(http_requests_total{status=~\"5..\"}[5m])"}
  After:  {"value": 0.089, ..., "sre_insight": {
              "severity": "critical",
              "interpretation": "Error rate at 8.9% — 8.9× above the 1% threshold",
              "pattern": "high_error_rate",
              "next_step": "Check logs for connection pool errors; restart if confirmed"
          }}
"""

import re
from typing import Any

# ── Thresholds ────────────────────────────────────────────────────────────────

_CPU_CRITICAL       = 0.90          # 90 %
_CPU_WARNING        = 0.50          # 50 %

_MEM_CRITICAL       = 1_500_000_000 # 1.5 GB bytes
_MEM_WARNING        =   500_000_000 # 500 MB bytes

_ERR_CRITICAL       = 0.10          # 10 % ratio
_ERR_WARNING        = 0.05          # 5 % ratio
_ERR_SLO            = 0.01          # 1 % SLO boundary

_LATENCY_CRITICAL   = 2.0           # p99 seconds
_LATENCY_WARNING    = 1.0           # p99 seconds

_RESTART_CRASHLOOP  = 5             # restart count
_UPTIME_FRESH_S     = 300           # seconds — "recently restarted"

# ── Log pattern signatures ────────────────────────────────────────────────────
# Each entry: (id, compiled_regex, short_label, actionable_hint)

_LOG_SIGS: list[tuple[str, re.Pattern, str, str]] = [
    (
        "connection_pool_exhaustion",
        re.compile(r"connection.pool|max.connect|too many connect|pool.exhaust|acquire.*timeout", re.I),
        "Connection pool exhausted",
        "Restart clears stale connections; also review DB/upstream connection limits",
    ),
    (
        "out_of_memory",
        re.compile(r"out.of.memory|OutOfMemoryError|OOMKilled|heap.space|GC overhead|cannot allocate", re.I),
        "OOM / heap exhaustion",
        "Restart reclaims memory; escalate if memory spikes back within 10 min",
    ),
    (
        "crash_restart",
        re.compile(r"panic:|fatal error|SIGSEGV|signal: killed|core dumped", re.I),
        "Process crash / panic",
        "Check stack trace in logs; crash-loop likely if restart_count is high",
    ),
    (
        "timeout",
        re.compile(r"timed?.?out|deadline exceeded|context canceled|read timeout|write timeout", re.I),
        "Timeout pattern",
        "Check downstream service health; may need to scale or fix a dependency",
    ),
    (
        "null_dereference",
        re.compile(r"NullPointerException|null pointer|nil pointer dereference", re.I),
        "Null pointer / nil dereference",
        "Likely uninitialized state — restart may resolve; check recent deployments",
    ),
    (
        "disk_full",
        re.compile(r"no space left|disk full|ENOSPC", re.I),
        "Disk full",
        "Run disk_usage diagnostic; clean up or extend volume before restarting",
    ),
]


class SREInterpreter:
    """
    Enriches raw tool results with SRE domain knowledge.

    Usage:
        interpreter = SREInterpreter()
        enriched = interpreter.interpret("get_metrics", params, raw_output_dict)
        # enriched has all original keys plus "sre_insight"
    """

    def interpret(
        self,
        tool_name: str,
        params: dict[str, Any],
        result: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Return a shallow copy of *result* with an added ``sre_insight`` key.
        Never raises — if interpretation fails the original result is returned
        unchanged so the agent loop is never disrupted.
        """
        enriched = dict(result)
        try:
            handler = {
                "get_metrics":        self._metrics,
                "get_recent_logs":    self._logs,
                "get_service_status": self._service_status,
                "run_diagnostic":     self._diagnostic,
                "restart_service":    self._restart,
                "scale_service":      self._scale,
                "escalate":           self._escalate,
            }.get(tool_name)
            if handler:
                enriched["sre_insight"] = handler(params, result)
        except Exception:
            pass  # silently skip — correctness of agent loop takes priority
        return enriched

    # ── Per-tool interpreters ─────────────────────────────────────────────────

    def _metrics(self, params: dict, result: dict) -> dict:
        query  = params.get("query", "")
        value  = result.get("value")
        status = result.get("status", "")

        if status in ("connection_error", "timeout", "http_error", "no_data", "query_error"):
            return {
                "severity":       "warning",
                "interpretation": f"Prometheus unavailable ({status}) — metrics missing",
                "next_step":      "Continue with log-based diagnosis; verify Prometheus connectivity",
            }

        if value is None:
            return {
                "severity":       "info",
                "interpretation": "No metric value returned for this query",
                "next_step":      "Try a different PromQL expression or check the metric name",
            }

        mtype = _classify_metric(query)

        if mtype == "cpu":
            pct = value * 100
            if value >= _CPU_CRITICAL:
                return {
                    "severity":       "critical",
                    "metric_type":    "cpu",
                    "interpretation": f"CPU at {pct:.1f}% — CRITICAL (threshold: 90%)",
                    "pattern":        "cpu_saturation",
                    "next_step":      "Restart clears goroutine leaks and busy-loops; scale if CPU stays high post-restart",
                }
            if value >= _CPU_WARNING:
                return {
                    "severity":       "warning",
                    "metric_type":    "cpu",
                    "interpretation": f"CPU at {pct:.1f}% — elevated (threshold: 50%)",
                    "next_step":      "Monitor trend; run connection_count diagnostic to rule out connection pressure",
                }
            return {
                "severity":       "ok",
                "metric_type":    "cpu",
                "interpretation": f"CPU at {pct:.1f}% — within normal bounds",
                "next_step":      "No CPU action needed",
            }

        if mtype == "memory":
            mb = value / 1_000_000
            if value >= _MEM_CRITICAL:
                return {
                    "severity":       "critical",
                    "metric_type":    "memory",
                    "interpretation": f"Memory at {mb:.0f} MB — CRITICAL (threshold: 1500 MB)",
                    "pattern":        "memory_leak",
                    "next_step":      "Restart reclaims memory; escalate if it spikes back within 10 min (active leak)",
                }
            if value >= _MEM_WARNING:
                return {
                    "severity":       "warning",
                    "metric_type":    "memory",
                    "interpretation": f"Memory at {mb:.0f} MB — above alert threshold (500 MB)",
                    "next_step":      "Check logs for OOM events and heap warnings",
                }
            return {
                "severity":       "ok",
                "metric_type":    "memory",
                "interpretation": f"Memory at {mb:.0f} MB — within normal bounds",
                "next_step":      "No memory action needed",
            }

        if mtype == "error_rate":
            is_ratio = "/" in query
            if is_ratio:
                pct     = value * 100
                x_above = value / _ERR_SLO if _ERR_SLO > 0 else 0
                if value >= _ERR_CRITICAL:
                    return {
                        "severity":       "critical",
                        "metric_type":    "error_rate",
                        "interpretation": f"Error rate {pct:.1f}% — CRITICAL ({x_above:.1f}× above 1% SLO)",
                        "pattern":        "high_error_rate",
                        "next_step":      "Check logs for connection pool exhaustion or downstream failure; restart service",
                    }
                if value >= _ERR_WARNING:
                    return {
                        "severity":       "warning",
                        "metric_type":    "error_rate",
                        "interpretation": f"Error rate {pct:.1f}% — elevated ({x_above:.1f}× above 1% SLO)",
                        "next_step":      "Investigate recurring error type in logs before acting",
                    }
                if value >= _ERR_SLO:
                    return {
                        "severity":       "warning",
                        "metric_type":    "error_rate",
                        "interpretation": f"Error rate {pct:.2f}% — above SLO boundary (1%)",
                        "next_step":      "Collect logs before acting; may self-recover",
                    }
                return {
                    "severity":       "ok",
                    "metric_type":    "error_rate",
                    "interpretation": f"Error rate {pct:.2f}% — within SLO",
                    "next_step":      "Error rate normal — look elsewhere for the alert source",
                }
            # Raw req/s (no division) — informational only
            return {
                "severity":       "info",
                "metric_type":    "error_rate_raw",
                "interpretation": f"Raw error request rate: {value:.4f} req/s",
                "next_step":      "Use a ratio query (errors / total) for threshold comparison",
            }

        if mtype == "latency":
            if value >= _LATENCY_CRITICAL:
                return {
                    "severity":       "critical",
                    "metric_type":    "latency",
                    "interpretation": f"p99 latency {value:.2f}s — CRITICAL (threshold: 2s)",
                    "pattern":        "high_latency",
                    "next_step":      "Check CPU saturation and downstream dependency health",
                }
            if value >= _LATENCY_WARNING:
                return {
                    "severity":       "warning",
                    "metric_type":    "latency",
                    "interpretation": f"p99 latency {value:.2f}s — above SLO (1s)",
                    "next_step":      "May be caused by CPU pressure or a slow upstream; investigate before acting",
                }
            return {
                "severity":       "ok",
                "metric_type":    "latency",
                "interpretation": f"p99 latency {value:.3f}s — within SLO",
                "next_step":      "Latency normal",
            }

        return {
            "severity":       "info",
            "metric_type":    "unknown",
            "interpretation": f"Metric value: {value}",
            "next_step":      "Compare against the expected baseline for this metric",
        }

    def _logs(self, params: dict, result: dict) -> dict:
        error_summary  = result.get("error_summary", {})
        total_errors   = error_summary.get("total_error_lines", 0)
        pattern_counts = error_summary.get("pattern_counts", {})
        logs           = result.get("logs", [])

        # Scan raw log text for SRE-specific signatures
        all_text     = "\n".join(logs)
        matched_sigs = [
            {"pattern": sig_id, "label": label, "hint": hint}
            for sig_id, sig_re, label, hint in _LOG_SIGS
            if sig_re.search(all_text)
        ]

        if not total_errors and not matched_sigs:
            return {
                "severity":       "ok",
                "interpretation": f"No error patterns in {result.get('line_count', 0)} log lines",
                "next_step":      "Logs clean — check metrics for the alert signal",
            }

        parts: list[str] = []
        if total_errors:
            parts.append(f"{total_errors} error lines found")
            if pattern_counts:
                top = sorted(pattern_counts.items(), key=lambda x: x[1], reverse=True)[:3]
                parts.append("Top patterns: " + ", ".join(f"{k}×{v}" for k, v in top))

        sev          = "warning"
        primary_hint = "Investigate error lines before acting"

        if matched_sigs:
            _critical_sigs = {"out_of_memory", "crash_restart"}
            if any(s["pattern"] in _critical_sigs for s in matched_sigs):
                sev = "critical"
            primary_hint = matched_sigs[0]["hint"]
            parts.append(
                "Root-cause signatures: " + "; ".join(s["label"] for s in matched_sigs)
            )

        return {
            "severity":          sev,
            "interpretation":    ". ".join(parts),
            "matched_signatures": [s["pattern"] for s in matched_sigs],
            "signature_hints":   {s["pattern"]: s["hint"] for s in matched_sigs},
            "next_step":         primary_hint,
        }

    def _service_status(self, params: dict, result: dict) -> dict:
        running        = result.get("running", False)
        restart_count  = result.get("restart_count", 0)
        uptime_seconds = result.get("uptime_seconds")
        status         = result.get("status", "unknown")

        if not running:
            return {
                "severity":       "critical",
                "interpretation": f"Service is DOWN (status: {status})",
                "pattern":        "service_down",
                "next_step":      "Restart service immediately; then check logs for crash cause",
            }

        parts: list[str] = []
        sev     = "ok"
        pattern = None
        hint    = "Service is running normally"

        if restart_count >= _RESTART_CRASHLOOP:
            sev     = "critical"
            pattern = "crash_loop"
            parts.append(f"Restart count {restart_count} — CRASH LOOP suspected")
            hint = "CrashLoopBackOff pattern. Check logs for panic/OOM. Escalate if restarts recur rapidly."
        elif restart_count > 0:
            sev = "warning"
            parts.append(f"Restart count {restart_count} — service has restarted")
            hint = "Service restarted recently; verify stability before assuming resolved"

        if uptime_seconds is not None:
            if uptime_seconds < _UPTIME_FRESH_S:
                mins = uptime_seconds / 60
                if sev == "ok":
                    sev = "warning"
                parts.append(f"Uptime only {mins:.1f} min — recently restarted")
                if not pattern:
                    hint = "Service just restarted — allow stabilization then re-check metrics"
            else:
                hours = uptime_seconds / 3600
                parts.append(f"Uptime {hours:.1f} h")

        if not parts:
            parts.append("Running normally")

        insight: dict[str, Any] = {
            "severity":       sev,
            "interpretation": ". ".join(parts),
            "next_step":      hint,
        }
        if pattern:
            insight["pattern"] = pattern
        return insight

    def _diagnostic(self, params: dict, result: dict) -> dict:
        check  = result.get("check", params.get("check", ""))
        status = result.get("status", "")

        if check == "alert_status":
            firing = result.get("alert_firing", True)
            phase  = result.get("scenario_phase", "")
            if not firing:
                return {
                    "severity":       "ok",
                    "interpretation": "Alert RESOLVED — remediation was successful",
                    "pattern":        "resolved",
                    "next_step":      "Call complete_incident with outcome=RESOLVED",
                }
            return {
                "severity":       "critical",
                "interpretation": f"Alert STILL FIRING (phase: {phase}) — remediation incomplete",
                "pattern":        "still_firing",
                "next_step":      "Collect more data or try an additional remediation; escalate if stuck after 3 attempts",
            }

        if check == "error_rate":
            rate = result.get("error_rate_percent")
            if rate is None:
                return {"severity": "info", "interpretation": "No error rate data", "next_step": "Check Prometheus"}
            if rate >= 5.0:
                return {
                    "severity":       "critical",
                    "interpretation": f"Error rate {rate:.1f}% — CRITICAL (≥5%)",
                    "next_step":      "Restart service to clear connection pool or transient errors",
                }
            if rate >= 1.0:
                return {
                    "severity":       "warning",
                    "interpretation": f"Error rate {rate:.1f}% — elevated (≥1%)",
                    "next_step":      "Investigate cause; restart if logs confirm connection pool issue",
                }
            return {
                "severity":       "ok",
                "interpretation": f"Error rate {rate:.2f}% — within SLO (<1%)",
                "next_step":      "Verify alert resolved with run_diagnostic check=alert_status",
            }

        if check == "memory_pressure":
            used_pct = result.get("used_percent", 0)
            if status == "critical":
                return {
                    "severity":       "critical",
                    "interpretation": f"System memory at {used_pct}% — CRITICAL (≥90%)",
                    "next_step":      "Restart the memory-consuming service immediately",
                }
            if status == "warning":
                return {
                    "severity":       "warning",
                    "interpretation": f"System memory at {used_pct}% — elevated (≥80%)",
                    "next_step":      "Monitor; restart if trending upward",
                }
            return {
                "severity":       "ok",
                "interpretation": f"System memory at {used_pct}% — OK",
                "next_step":      "System memory healthy; check container-level metrics",
            }

        if check == "connection_count":
            total = result.get("total_connections", 0)
            if status == "critical":
                return {
                    "severity":       "critical",
                    "interpretation": f"{total} open connections — CRITICAL (≥5000)",
                    "pattern":        "connection_exhaustion",
                    "next_step":      "Restart to clear connections; scale if traffic is legitimate",
                }
            if status == "warning":
                return {
                    "severity":       "warning",
                    "interpretation": f"{total} open connections — elevated (≥1000)",
                    "next_step":      "Monitor; review connection pool settings",
                }
            return {
                "severity":       "ok",
                "interpretation": f"{total} open connections — normal",
                "next_step":      "Connection count healthy; look elsewhere",
            }

        if check == "disk_usage":
            used_pct = result.get("used_percent", 0)
            if status == "critical":
                return {
                    "severity":       "critical",
                    "interpretation": f"Disk at {used_pct}% — CRITICAL (≥95%)",
                    "next_step":      "Free disk immediately — purge logs or extend volume",
                }
            if status == "warning":
                return {
                    "severity":       "warning",
                    "interpretation": f"Disk at {used_pct}% — elevated (≥85%)",
                    "next_step":      "Plan disk cleanup; not immediately critical",
                }
            return {
                "severity":       "ok",
                "interpretation": f"Disk at {used_pct}% — OK",
                "next_step":      "Disk healthy",
            }

        return {
            "severity":       "info",
            "interpretation": f"Diagnostic '{check}' returned status: {status}",
            "next_step":      "Review raw result above for details",
        }

    def _restart(self, params: dict, result: dict) -> dict:
        success = result.get("success", False)
        service = params.get("service", "service")
        if success:
            return {
                "severity":       "info",
                "interpretation": f"'{service}' restarted successfully",
                "next_step": (
                    "Now verify recovery: "
                    "(1) get_metrics to re-check error rate / CPU / memory, "
                    "(2) run_diagnostic check=alert_status to confirm alert resolved"
                ),
            }
        error = result.get("error", "unknown error")
        return {
            "severity":       "warning",
            "interpretation": f"Restart of '{service}' failed: {error}",
            "next_step":      "Check Docker daemon; try get_service_status to see container state",
        }

    def _scale(self, params: dict, result: dict) -> dict:
        success  = result.get("success", False)
        service  = params.get("service", "service")
        replicas = params.get("replicas", "?")
        if success:
            return {
                "severity":       "info",
                "interpretation": f"'{service}' scaled to {replicas} replicas",
                "next_step":      "Re-check metrics to confirm load distribution improved",
            }
        error = result.get("error", result.get("stderr", "unknown"))[:120]
        return {
            "severity":       "warning",
            "interpretation": f"Scale of '{service}' to {replicas} replicas failed: {error}",
            "next_step":      "Check Docker Compose availability; try restart_service as fallback",
        }

    def _escalate(self, params: dict, result: dict) -> dict:
        return {
            "severity":       "info",
            "interpretation": "Escalation triggered — on-call team notified",
            "next_step":      "Call complete_incident with outcome=ESCALATED",
        }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _classify_metric(query: str) -> str:
    """Classify a PromQL query string into a broad metric type."""
    q = query.lower()
    if "cpu" in q:
        return "cpu"
    if "memory" in q or "mem_" in q:
        return "memory"
    if "5.." in q or "http_requests" in q or "error_rate" in q or "error_count" in q:
        return "error_rate"
    if "duration" in q or "latency" in q or "p99" in q or "p95" in q or "quantile" in q or "histogram" in q:
        return "latency"
    return "unknown"
