/**
 * Smart tool call + result display.
 *
 * Each pair renders as a compact row:
 *   [icon] tool_name  key_arg  →  result_summary
 *
 * Full JSON is available in a collapsible "details" section.
 */

import { useState } from "react";
import { clsx } from "clsx";
import {
  BarChart2, Terminal, Activity, RefreshCw, Layers,
  Stethoscope, AlertTriangle, CheckCircle2, ChevronDown,
  ChevronRight, Loader2,
} from "lucide-react";
import type { ContentBlock } from "@/types/incident";

type ToolUseBlock   = Extract<ContentBlock, { type: "tool_use" }>;
type ToolResultBlock = Extract<ContentBlock, { type: "tool_result" }>;

// ── Tool metadata ─────────────────────────────────────────────────────────────

interface ToolMeta {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  border: string;
  iconColor: string;
  bg: string;
}

const TOOL_META: Record<string, ToolMeta> = {
  get_metrics:        { icon: BarChart2,      label: "Query Metrics",   border: "border-violet-800/40",  iconColor: "text-violet-400",  bg: "bg-violet-950/20"  },
  get_recent_logs:    { icon: Terminal,       label: "Fetch Logs",      border: "border-blue-800/40",    iconColor: "text-blue-400",    bg: "bg-blue-950/20"    },
  get_service_status: { icon: Activity,       label: "Service Status",  border: "border-blue-800/40",    iconColor: "text-blue-400",    bg: "bg-blue-950/20"    },
  restart_service:    { icon: RefreshCw,      label: "Restart Service", border: "border-orange-800/40",  iconColor: "text-orange-400",  bg: "bg-orange-950/20"  },
  scale_service:      { icon: Layers,         label: "Scale Service",   border: "border-orange-800/40",  iconColor: "text-orange-400",  bg: "bg-orange-950/20"  },
  run_diagnostic:     { icon: Stethoscope,    label: "Run Diagnostic",  border: "border-purple-800/40",  iconColor: "text-purple-400",  bg: "bg-purple-950/20"  },
  escalate:           { icon: AlertTriangle,  label: "Escalate",        border: "border-red-800/40",     iconColor: "text-red-400",     bg: "bg-red-950/20"     },
  complete_incident:  { icon: CheckCircle2,   label: "Complete",        border: "border-emerald-800/40", iconColor: "text-emerald-400", bg: "bg-emerald-950/20" },
};

const DEFAULT_META: ToolMeta = {
  icon: Loader2, label: "Tool", border: "border-zinc-700/40", iconColor: "text-zinc-400", bg: "bg-zinc-900/20",
};

// ── Key-arg extraction ────────────────────────────────────────────────────────

function getKeyArg(name: string, input: Record<string, unknown>): string {
  switch (name) {
    case "get_metrics":        return truncate(String(input.query ?? ""), 60);
    case "get_recent_logs":    return `${input.service} (${input.lines ?? 100} lines)`;
    case "get_service_status": return String(input.service ?? "");
    case "restart_service":    return String(input.service ?? "");
    case "scale_service":      return `${input.service} to ${input.replicas} replicas`;
    case "run_diagnostic":     return String(input.check ?? "");
    case "escalate":           return `${input.severity} — ${truncate(String(input.reason ?? ""), 50)}`;
    case "complete_incident":  return String(input.outcome ?? "");
    default:                   return "";
  }
}

function truncate(s: string, max: number) {
  return s.length > max ? s.slice(0, max) + "…" : s;
}

// ── Result summary extraction ─────────────────────────────────────────────────

interface ResultSummary {
  badge: React.ReactNode;
  detail?: string;
}

function parseResult(toolName: string, rawContent: string): ResultSummary {
  let data: Record<string, unknown> = {};
  try { data = JSON.parse(rawContent); } catch { /* raw string */ }

  // Handle nested output field (our registry wraps results)
  const output = (data.output ?? data) as Record<string, unknown>;

  switch (toolName) {
    case "get_metrics": {
      const val = (output.value as number) ?? 0;
      const isHigh = val > 0.05;
      return {
        badge: <MetricBadge value={val} high={isHigh} />,
        detail: output.status as string,
      };
    }
    case "get_recent_logs": {
      const errCount = (output.error_summary as Record<string,unknown>)?.total_error_lines as number ?? 0;
      const lineCount = output.line_count as number ?? 0;
      const source    = output.source as string;
      return {
        badge: errCount > 0
          ? <StatusBadge color="red"   label={`${errCount} errors`} />
          : <StatusBadge color="green" label="No errors" />,
        detail: `${lineCount} lines${source === "mock" ? " (mock)" : ""}`,
      };
    }
    case "get_service_status": {
      const running = output.running as boolean;
      const status  = output.status as string;
      return {
        badge: running
          ? <StatusBadge color="green" label="running" />
          : <StatusBadge color="red"   label={status ?? "down"} />,
        detail: output.uptime_seconds
          ? `up ${Math.round((output.uptime_seconds as number) / 60)}m`
          : undefined,
      };
    }
    case "restart_service": {
      const success = data.success !== false && output.success !== false;
      return {
        badge: success
          ? <StatusBadge color="green"  label="restarted" />
          : <StatusBadge color="red"    label="failed" />,
        detail: success ? String(output.new_status ?? "") : String(data.error ?? output.error ?? ""),
      };
    }
    case "scale_service": {
      const success = data.success !== false && output.success !== false;
      return {
        badge: success
          ? <StatusBadge color="green" label="scaled" />
          : <StatusBadge color="red"   label="failed" />,
      };
    }
    case "run_diagnostic": {
      const check = (output.check as string) ?? "";
      if (check === "alert_status") {
        const firing = output.alert_firing as boolean;
        const phase  = output.scenario_phase as string;
        return {
          badge: firing
            ? <StatusBadge color="red"   label="still firing" />
            : <StatusBadge color="green" label="resolved" />,
          detail: phase,
        };
      }
      if (check === "error_rate") {
        const rate   = output.error_rate_percent as number;
        const status = output.status as string;
        return {
          badge: <MetricBadge value={rate} high={rate > 1} suffix="%" />,
          detail: status,
        };
      }
      const status = (output.status as string) ?? (data.status as string);
      const color  = status === "ok" ? "green" : status === "warning" ? "yellow" : "red";
      return { badge: <StatusBadge color={color as "green" | "yellow" | "red"} label={status ?? "—"} /> };
    }
    case "escalate": {
      return { badge: <StatusBadge color="red" label="escalated" /> };
    }
    case "complete_incident": {
      const outcome = (output.outcome as string) ?? "RESOLVED";
      const color = outcome === "RESOLVED" ? "green" : outcome === "ESCALATED" ? "yellow" : "red";
      return { badge: <StatusBadge color={color as "green" | "yellow" | "red"} label={outcome} /> };
    }
    default: {
      const success = data.success !== false;
      return { badge: <StatusBadge color={success ? "green" : "red"} label={success ? "ok" : "error"} /> };
    }
  }
}

// ── Small badge components ────────────────────────────────────────────────────

const BADGE_COLORS = {
  green:  "bg-emerald-900/50 text-emerald-300 border-emerald-700/40",
  red:    "bg-red-900/50 text-red-300 border-red-700/40",
  yellow: "bg-amber-900/50 text-amber-300 border-amber-700/40",
  blue:   "bg-blue-900/50 text-blue-300 border-blue-700/40",
};

function StatusBadge({ color, label }: { color: keyof typeof BADGE_COLORS; label: string }) {
  return (
    <span className={clsx("inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide", BADGE_COLORS[color])}>
      {label}
    </span>
  );
}

function MetricBadge({ value, high, suffix = "" }: { value: number; high: boolean; suffix?: string }) {
  return (
    <span className={clsx(
      "inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-mono font-medium",
      high ? BADGE_COLORS.red : BADGE_COLORS.green,
    )}>
      {typeof value === "number" ? value.toFixed(4) : value}{suffix}
    </span>
  );
}

// ── Main export: combined ToolPair ────────────────────────────────────────────

export interface ToolPairProps {
  call: ToolUseBlock;
  result?: ToolResultBlock;
}

export function ToolPair({ call, result }: ToolPairProps) {
  const [open, setOpen] = useState(false);
  const meta = TOOL_META[call.name] ?? DEFAULT_META;
  const Icon = meta.icon;
  const keyArg = getKeyArg(call.name, call.input);

  const pending = !result;
  const summary = result ? parseResult(call.name, result.content) : null;

  return (
    <div className={clsx("rounded border text-xs", meta.border, meta.bg)}>
      {/* Header row */}
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-white/5 transition-colors"
      >
        <Icon className={clsx("h-3.5 w-3.5 shrink-0", meta.iconColor)} />

        <span className={clsx("font-mono font-medium shrink-0", meta.iconColor)}>
          {call.name}
        </span>

        {keyArg && (
          <span className="truncate text-zinc-500 font-mono">
            {keyArg}
          </span>
        )}

        <span className="ml-auto flex items-center gap-2 shrink-0">
          {pending ? (
            <span className="text-zinc-600 italic">pending…</span>
          ) : summary ? (
            <>
              {summary.badge}
              {summary.detail && (
                <span className="text-zinc-500">{summary.detail}</span>
              )}
            </>
          ) : null}
          {open
            ? <ChevronDown  className="h-3 w-3 text-zinc-600" />
            : <ChevronRight className="h-3 w-3 text-zinc-600" />
          }
        </span>
      </button>

      {/* Expanded details */}
      {open && (
        <div className="border-t border-zinc-700/30 px-3 py-2 space-y-2">
          <div>
            <p className="mb-1 text-[10px] font-medium uppercase tracking-wide text-zinc-600">Input</p>
            <pre className="overflow-x-auto font-mono text-[11px] text-zinc-400 leading-relaxed">
              {JSON.stringify(call.input, null, 2)}
            </pre>
          </div>
          {result && (() => {
            let parsed: Record<string, unknown> = {};
            try { parsed = JSON.parse(result.content) as Record<string, unknown>; } catch { /* ok */ }
            const insight = parsed.sre_insight as Record<string, string> | undefined;
            const outputOnly = insight ? { ...parsed, sre_insight: undefined } : parsed;
            return (
              <>
                <div>
                  <p className="mb-1 text-[10px] font-medium uppercase tracking-wide text-zinc-600">Output</p>
                  <pre className="overflow-x-auto font-mono text-[11px] text-zinc-400 leading-relaxed">
                    {JSON.stringify(outputOnly, null, 2)}
                  </pre>
                </div>
                {insight && (insight.interpretation || insight.next_step) && (
                  <div className="rounded border border-violet-800/30 bg-violet-950/20 px-2.5 py-2">
                    <p className="mb-1 text-[10px] font-medium uppercase tracking-wide text-violet-500">SRE Insight</p>
                    {insight.interpretation && (
                      <p className="text-[11px] text-violet-300">{insight.interpretation}</p>
                    )}
                    {insight.next_step && (
                      <p className="mt-0.5 text-[11px] text-zinc-400 italic">{insight.next_step}</p>
                    )}
                  </div>
                )}
              </>
            );
          })()}
        </div>
      )}
    </div>
  );
}

// ── Legacy exports (used nowhere now, but kept for safety) ────────────────────

export function ToolCallBlock({ block }: { block: ToolUseBlock }) {
  return <ToolPair call={block} />;
}

export function ToolResultBlock({ block }: { block: ToolResultBlock }) {
  // Standalone result (not paired) — show as raw collapsible
  return (
    <details className="rounded border border-emerald-800/40 bg-emerald-950/20 text-xs">
      <summary className="cursor-pointer px-3 py-1.5 font-mono font-medium text-emerald-300 hover:bg-emerald-900/20">
        tool_result
      </summary>
      <div className="border-t border-emerald-800/30 px-3 py-2">
        <pre className="overflow-x-auto font-mono text-[11px] text-zinc-400">
          {(() => {
            try { return JSON.stringify(JSON.parse(block.content), null, 2); }
            catch { return block.content; }
          })()}
        </pre>
      </div>
    </details>
  );
}
