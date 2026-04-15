import { clsx } from "clsx";
import type { TranscriptMessage, ContentBlock } from "@/types/incident";
import { ToolCallBlock, ToolResultBlock } from "./ToolCallBlock";
import { Markdown } from "./Markdown";

// ── Incident report extraction ────────────────────────────────────────────────

export interface ParsedReport {
  summary?: string;
  root_cause?: string;
  outcome?: string;
  actions_taken?: string[];
  recommendations?: string[];
}

export function extractReport(text: string): { prose: string; thinking: string; report: ParsedReport | null } {
  // Strip <think>...</think> blocks (qwen3 internal reasoning)
  let thinking = "";
  let remaining = text.replace(/<think>([\s\S]*?)<\/think>/gi, (_, inner) => {
    thinking = inner.trim();
    return "";
  }).trim();

  // Try JSON ```json ... ``` block
  const jsonMatch = remaining.match(/```json\s*([\s\S]*?)\s*```/);
  if (jsonMatch) {
    try {
      const report = JSON.parse(jsonMatch[1]) as ParsedReport;
      const prose = remaining.slice(0, remaining.indexOf("```json")).trim();
      return { prose, thinking, report };
    } catch {
      // fall through
    }
  }

  // Try <incident_report>...</incident_report> XML
  const xmlMatch = remaining.match(/<incident_report>([\s\S]*?)<\/incident_report>/i);
  if (xmlMatch) {
    const xml = xmlMatch[0];
    const prose = remaining.slice(0, remaining.indexOf("<incident_report>")).trim();

    const field = (tag: string) => {
      const m = xml.match(new RegExp(`<${tag}>([\\s\\S]*?)<\\/${tag}>`, "i"));
      return m ? m[1].trim() : undefined;
    };
    const list = (containerTag: string, itemTag: string): string[] => {
      const containerMatch = xml.match(new RegExp(`<${containerTag}>([\\s\\S]*?)<\\/${containerTag}>`, "i"));
      if (!containerMatch) return [];
      return [...containerMatch[1].matchAll(new RegExp(`<${itemTag}>([\\s\\S]*?)<\\/${itemTag}>`, "gi"))].map(
        (m) => m[1].trim(),
      );
    };

    return {
      prose,
      thinking,
      report: {
        summary: field("summary"),
        root_cause: field("root_cause"),
        outcome: field("outcome"),
        actions_taken: list("actions_taken", "action"),
        recommendations: list("recommendations", "recommendation"),
      },
    };
  }

  return { prose: remaining, thinking, report: null };
}

// ── Final report card ─────────────────────────────────────────────────────────

const outcomeStyle: Record<string, string> = {
  RESOLVED:  "border-emerald-700 bg-emerald-950/40 text-emerald-300",
  ESCALATED: "border-amber-700 bg-amber-950/40 text-amber-300",
  FAILED:    "border-red-700 bg-red-950/40 text-red-300",
};

const outcomeLabel: Record<string, string> = {
  RESOLVED:  "Resolved",
  ESCALATED: "Escalated",
  FAILED:    "Failed",
};

export function FinalReportCard({ report }: { report: ParsedReport }) {
  const rawOutcome = report.outcome?.toUpperCase();
  // Only show a badge for known terminal outcomes; skip if missing/unknown
  const outcome = rawOutcome && outcomeStyle[rawOutcome] ? rawOutcome : null;
  const style = outcome ? outcomeStyle[outcome] : "border-zinc-700 bg-zinc-800/40 text-zinc-300";

  return (
    <div className="mt-3 rounded-lg border border-zinc-700 bg-zinc-900 overflow-hidden">
      {/* header */}
      <div className={clsx("flex items-center gap-2 px-3 py-2 border-b border-zinc-700/60", outcome ? style.split(" ").slice(0, 2).join(" ") : "bg-zinc-800/40")}>
        {outcome && (
          <span className={clsx("text-xs font-bold uppercase tracking-wide", style.split(" ")[2])}>
            {outcomeLabel[outcome] ?? outcome}
          </span>
        )}
        <span className="text-xs text-zinc-400">Incident Report</span>
      </div>

      <div className="px-3 py-3 space-y-3">
        {report.summary && (
          <div>
            <p className="mb-0.5 text-xs font-semibold uppercase tracking-wide text-zinc-500">Summary</p>
            <p className="text-sm text-zinc-300">{report.summary}</p>
          </div>
        )}

        {report.root_cause && (
          <div>
            <p className="mb-0.5 text-xs font-semibold uppercase tracking-wide text-zinc-500">Root Cause</p>
            <p className="text-sm text-zinc-400">{report.root_cause}</p>
          </div>
        )}

        {report.actions_taken && report.actions_taken.length > 0 && (
          <div>
            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-500">Actions Taken</p>
            <ul className="space-y-1">
              {report.actions_taken.map((a, i) => (
                <li key={i} className="flex gap-2 text-xs text-zinc-400">
                  <span className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-violet-500 mt-1.5" />
                  {a}
                </li>
              ))}
            </ul>
          </div>
        )}

        {report.recommendations && report.recommendations.length > 0 && (
          <div>
            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-500">Recommendations</p>
            <ul className="space-y-1">
              {report.recommendations.map((r, i) => (
                <li key={i} className="flex gap-2 text-xs text-zinc-400">
                  <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-600" />
                  {r}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Content renderer ──────────────────────────────────────────────────────────

function renderTextContent(text: string, role: string) {
  if (role !== "assistant") {
    return <Markdown text={text} className="text-zinc-300" />;
  }

  const { prose, thinking, report } = extractReport(text);

  return (
    <div className="space-y-1">
      {/* collapsible thinking block */}
      {thinking && (
        <details className="rounded border border-zinc-700/50 bg-zinc-800/30">
          <summary className="cursor-pointer px-3 py-1.5 text-xs text-zinc-500 hover:text-zinc-400 select-none">
            Model thinking…
          </summary>
          <div className="px-3 pb-2 border-t border-zinc-700/40 pt-2">
            <Markdown text={thinking} className="text-zinc-600 text-xs" />
          </div>
        </details>
      )}

      {/* prose text — rendered as markdown */}
      {prose && <Markdown text={prose} />}

      {/* structured report */}
      {report && <FinalReportCard report={report} />}
    </div>
  );
}

function renderContent(content: TranscriptMessage["content"], role: string) {
  if (typeof content === "string") {
    return renderTextContent(content, role);
  }

  return (
    <div className="space-y-1">
      {content.map((block, i) => {
        if (block.type === "text") {
          return <div key={i}>{renderTextContent(block.text, role)}</div>;
        }
        if (block.type === "tool_use") {
          return <ToolCallBlock key={i} block={block} />;
        }
        if (block.type === "tool_result") {
          return <ToolResultBlock key={i} block={block as Extract<ContentBlock, { type: "tool_result" }>} />;
        }
        return null;
      })}
    </div>
  );
}

// ── MessageBubble ─────────────────────────────────────────────────────────────

export function MessageBubble({ message }: { message: TranscriptMessage }) {
  const isAssistant = message.role === "assistant";

  return (
    <div className={clsx("flex gap-3", isAssistant ? "flex-row" : "flex-row-reverse")}>
      {/* avatar */}
      <div
        className={clsx(
          "mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded text-xs font-bold",
          isAssistant ? "bg-violet-800 text-violet-200" : "bg-zinc-700 text-zinc-300",
        )}
      >
        {isAssistant ? "AI" : "U"}
      </div>

      <div
        className={clsx(
          "max-w-[85%] rounded-lg px-3 py-2",
          isAssistant ? "bg-zinc-800" : "bg-zinc-800/50",
        )}
      >
        {renderContent(message.content, message.role)}
      </div>
    </div>
  );
}
