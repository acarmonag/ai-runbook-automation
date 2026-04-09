import type { TranscriptMessage } from "@/types/incident";
import { MessageBubble } from "@/components/transcript/MessageBubble";

export function ReasoningTranscript({ messages }: { messages: TranscriptMessage[] }) {
  if (!messages.length) {
    return <p className="text-sm text-zinc-500">No reasoning transcript available.</p>;
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-zinc-500">{messages.length} messages</p>
      {messages.map((msg, i) => (
        <MessageBubble key={i} message={msg} />
      ))}
    </div>
  );
}
