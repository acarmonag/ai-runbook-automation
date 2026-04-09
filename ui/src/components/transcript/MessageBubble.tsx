import { clsx } from "clsx";
import type { TranscriptMessage, ContentBlock } from "@/types/incident";
import { ToolCallBlock, ToolResultBlock } from "./ToolCallBlock";

function renderContent(content: TranscriptMessage["content"]) {
  if (typeof content === "string") {
    return <p className="whitespace-pre-wrap text-sm text-zinc-300">{content}</p>;
  }

  return (
    <div>
      {content.map((block, i) => {
        if (block.type === "text") {
          return (
            <p key={i} className="whitespace-pre-wrap text-sm text-zinc-300">
              {block.text}
            </p>
          );
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
        {isAssistant ? "AI" : "→"}
      </div>

      <div
        className={clsx(
          "max-w-[85%] rounded-lg px-3 py-2",
          isAssistant ? "bg-zinc-800" : "bg-zinc-800/50",
        )}
      >
        {renderContent(message.content)}
      </div>
    </div>
  );
}
