/**
 * Reasoning Transcript — timeline view of the agent's investigation.
 *
 * Transforms the raw message list into a flat sequence of events:
 *   • text  — assistant analysis/thinking rendered as markdown
 *   • tool  — tool call + its result paired together
 *   • nudge — system nudge injected by the orchestrator
 *
 * Tool calls (in assistant messages) and their results (in subsequent user
 * messages) are correlated by tool_use_id so they render as a single row.
 */

import { Bot, MessageSquare } from "lucide-react";
import type { TranscriptMessage, ContentBlock } from "@/types/incident";
import { ToolPair } from "@/components/transcript/ToolCallBlock";
import { Markdown } from "@/components/transcript/Markdown";
import { FinalReportCard, extractReport } from "@/components/transcript/MessageBubble";

type ToolUseBlock    = Extract<ContentBlock, { type: "tool_use" }>;
type ToolResultBlock = Extract<ContentBlock, { type: "tool_result" }>;

// ── Timeline event types ──────────────────────────────────────────────────────

type TextEvent  = { kind: "text";  text: string;  timestamp?: string };
type ToolEvent  = { kind: "tool";  call: ToolUseBlock; result?: ToolResultBlock; timestamp?: string };
type NudgeEvent = { kind: "nudge"; text: string;  timestamp?: string };

type TimelineEvent = TextEvent | ToolEvent | NudgeEvent;

// ── Build timeline from raw messages ─────────────────────────────────────────

function buildTimeline(messages: TranscriptMessage[]): TimelineEvent[] {
  // Pass 1: collect all tool results keyed by tool_use_id
  const results = new Map<string, ToolResultBlock>();
  for (const msg of messages) {
    if (!Array.isArray(msg.content)) continue;
    for (const block of msg.content) {
      if (block.type === "tool_result") results.set(block.tool_use_id, block);
    }
  }

  // Pass 2: build flat event list from assistant messages + system nudges
  const events: TimelineEvent[] = [];

  for (const msg of messages) {
    const ts = msg.timestamp;

    if (msg.role === "assistant") {
      if (typeof msg.content === "string") {
        if (msg.content.trim()) events.push({ kind: "text", text: msg.content, timestamp: ts });
        continue;
      }
      for (const block of msg.content) {
        if (block.type === "text" && block.text.trim()) {
          events.push({ kind: "text", text: block.text, timestamp: ts });
        } else if (block.type === "tool_use") {
          events.push({ kind: "tool", call: block, result: results.get(block.id), timestamp: ts });
        }
      }
    } else if (msg.role === "user" && typeof msg.content === "string" && msg.content.trim()) {
      // String user messages are system-injected nudges — skip them in the timeline.
      // They are internal prompts to the LLM, not user-visible events.
    }
    // Array user messages (tool_result blocks) are handled via correlation above — skip
  }

  return events;
}

// ── Row wrapper ───────────────────────────────────────────────────────────────

function TimelineRow({ step, children }: { step: number; children: React.ReactNode }) {
  return (
    <div className="flex gap-3">
      {/* Step indicator + vertical line */}
      <div className="flex flex-col items-center">
        <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-zinc-800 border border-zinc-700 text-[9px] font-bold text-zinc-500">
          {step}
        </div>
        <div className="mt-1 w-px flex-1 bg-zinc-800" />
      </div>
      <div className="flex-1 pb-3 min-w-0">{children}</div>
    </div>
  );
}

// ── Text event renderer ───────────────────────────────────────────────────────

function TextEventRow({ event, step }: { event: TextEvent; step: number }) {
  const { prose, thinking, report } = extractReport(event.text);

  // If it's purely a final report card (no prose), skip prose
  return (
    <TimelineRow step={step}>
      <div className="space-y-2">
        {/* Model thinking */}
        {thinking && (
          <details className="rounded border border-zinc-700/50 bg-zinc-800/30">
            <summary className="cursor-pointer select-none px-3 py-1.5 text-xs text-zinc-500 hover:text-zinc-400">
              Model thinking…
            </summary>
            <div className="border-t border-zinc-700/40 px-3 pb-2 pt-2">
              <Markdown text={thinking} className="text-zinc-600" />
            </div>
          </details>
        )}

        {/* Prose analysis */}
        {prose && (
          <div className="rounded border border-zinc-800 bg-zinc-900/50 px-3 py-2.5">
            <div className="mb-1.5 flex items-center gap-1.5">
              <Bot className="h-3 w-3 text-violet-400" />
              <span className="text-[10px] font-medium uppercase tracking-wide text-zinc-500">
                Agent analysis
              </span>
            </div>
            <Markdown text={prose} />
          </div>
        )}

        {/* Structured report card */}
        {report && <FinalReportCard report={report} />}
      </div>
    </TimelineRow>
  );
}

// ── Tool event renderer ───────────────────────────────────────────────────────

function ToolEventRow({ event, step }: { event: ToolEvent; step: number }) {
  return (
    <TimelineRow step={step}>
      <ToolPair call={event.call} result={event.result} />
    </TimelineRow>
  );
}

// ── Nudge event renderer ──────────────────────────────────────────────────────

function NudgeEventRow({ event, step }: { event: NudgeEvent; step: number }) {
  return (
    <TimelineRow step={step}>
      <div className="rounded border border-zinc-700/30 bg-zinc-800/20 px-3 py-1.5 flex items-center gap-2">
        <MessageSquare className="h-3 w-3 text-zinc-600 shrink-0" />
        <span className="text-xs text-zinc-600 italic">{event.text}</span>
      </div>
    </TimelineRow>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function ReasoningTranscript({ messages }: { messages: TranscriptMessage[] }) {
  if (!messages.length) {
    return <p className="text-sm text-zinc-500">No reasoning transcript available.</p>;
  }

  const events = buildTimeline(messages);
  const toolCount = events.filter((e) => e.kind === "tool").length;
  const textCount = events.filter((e) => e.kind === "text").length;

  return (
    <div>
      <p className="mb-3 text-xs text-zinc-600">
        {toolCount} tool calls · {textCount} analysis blocks · {messages.length} raw messages
      </p>

      <div className="relative">
        {events.map((event, i) => {
          const step = i + 1;
          if (event.kind === "text")  return <TextEventRow  key={i} event={event} step={step} />;
          if (event.kind === "tool")  return <ToolEventRow  key={i} event={event} step={step} />;
          if (event.kind === "nudge") return <NudgeEventRow key={i} event={event} step={step} />;
          return null;
        })}

        {/* End marker */}
        <div className="flex gap-3">
          <div className="flex h-5 w-5 shrink-0 items-center justify-center">
            <div className="h-1.5 w-1.5 rounded-full bg-zinc-700" />
          </div>
          <span className="pb-1 text-xs text-zinc-600">End of transcript</span>
        </div>
      </div>
    </div>
  );
}
