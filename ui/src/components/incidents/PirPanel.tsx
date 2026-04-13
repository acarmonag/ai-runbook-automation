import type { PostIncidentReview } from "@/types/incident";
import { Markdown } from "@/components/transcript/Markdown";

interface PirPanelProps {
  pir: PostIncidentReview;
}

const priorityColor: Record<string, string> = {
  P1: "text-red-400",
  P2: "text-orange-400",
  P3: "text-yellow-400",
  P4: "text-zinc-400",
};

export function PirPanel({ pir }: PirPanelProps) {
  return (
    <div className="space-y-5 text-sm">
      {/* Header */}
      <div className="flex items-center gap-2">
        <span className={`font-bold text-base ${priorityColor[pir.severity] ?? "text-zinc-300"}`}>
          {pir.severity}
        </span>
        <span className="text-zinc-200 font-medium">{pir.title}</span>
      </div>

      {/* Root cause + impact */}
      <section>
        <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wide mb-1">Root Cause</h3>
        <Markdown text={pir.root_cause} />
      </section>

      {pir.impact && (
        <section>
          <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wide mb-1">Impact</h3>
          <Markdown text={pir.impact} />
        </section>
      )}

      {pir.resolution && (
        <section>
          <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wide mb-1">Resolution</h3>
          <Markdown text={pir.resolution} />
        </section>
      )}

      {/* Contributing factors */}
      {pir.contributing_factors?.length > 0 && (
        <section>
          <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wide mb-1">
            Contributing Factors
          </h3>
          <ul className="space-y-1">
            {pir.contributing_factors.map((f, i) => (
              <li key={i} className="flex gap-2 text-zinc-400">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-zinc-600" />
                <span>{f}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Timeline */}
      {pir.timeline?.length > 0 && (
        <section>
          <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wide mb-2">Timeline</h3>
          <ol className="border-l border-zinc-700 pl-4 space-y-2">
            {pir.timeline.map((item, i) => (
              <li key={i} className="relative">
                <span className="absolute -left-[1.125rem] top-1.5 h-2 w-2 rounded-full bg-zinc-600" />
                <span className="font-mono text-xs text-zinc-500 mr-2">{item.time}</span>
                <span className="text-zinc-300">{item.event}</span>
              </li>
            ))}
          </ol>
        </section>
      )}

      {/* Action items */}
      {pir.action_items?.length > 0 && (
        <section>
          <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wide mb-2">Action Items</h3>
          <ul className="space-y-2">
            {pir.action_items.map((item, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className={`mt-0.5 text-xs font-bold ${priorityColor[item.priority] ?? "text-zinc-400"}`}>
                  {item.priority}
                </span>
                <div>
                  <span className="text-zinc-300">{item.action}</span>
                  {item.owner && (
                    <span className="ml-2 text-xs text-zinc-500">@{item.owner}</span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Prevention */}
      {pir.prevention?.length > 0 && (
        <section>
          <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wide mb-1">Prevention</h3>
          <ul className="space-y-1">
            {pir.prevention.map((p, i) => (
              <li key={i} className="flex gap-2 text-zinc-400">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-600" />
                <span>{p}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
