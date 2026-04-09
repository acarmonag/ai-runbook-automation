import type { ContentBlock } from "@/types/incident";

type ToolUseBlock = Extract<ContentBlock, { type: "tool_use" }>;
type ToolResultBlock = Extract<ContentBlock, { type: "tool_result" }>;

export function ToolCallBlock({ block }: { block: ToolUseBlock }) {
  return (
    <details className="mt-2 rounded border border-violet-800/40 bg-violet-950/20">
      <summary className="cursor-pointer px-3 py-1.5 text-xs font-mono font-medium text-violet-300 hover:bg-violet-900/20">
        tool_use: {block.name}
      </summary>
      <div className="border-t border-violet-800/30 px-3 py-2">
        <pre className="overflow-x-auto text-xs text-zinc-400 font-mono">
          {JSON.stringify(block.input, null, 2)}
        </pre>
      </div>
    </details>
  );
}

export function ToolResultBlock({ block }: { block: ToolResultBlock }) {
  let parsed: unknown;
  try {
    parsed = JSON.parse(block.content);
  } catch {
    parsed = block.content;
  }

  return (
    <details className="mt-2 rounded border border-emerald-800/40 bg-emerald-950/20">
      <summary className="cursor-pointer px-3 py-1.5 text-xs font-mono font-medium text-emerald-300 hover:bg-emerald-900/20">
        tool_result
      </summary>
      <div className="border-t border-emerald-800/30 px-3 py-2">
        <pre className="overflow-x-auto text-xs text-zinc-400 font-mono">
          {typeof parsed === "string" ? parsed : JSON.stringify(parsed, null, 2)}
        </pre>
      </div>
    </details>
  );
}
