import { CheckCircle, XCircle, MinusCircle, FlaskConical } from "lucide-react";
import { clsx } from "clsx";
import type { ActionTaken, ActionResult } from "@/types/incident";
import { formatTimestamp } from "@/lib/format";

const resultConfig: Record<ActionResult, { icon: typeof CheckCircle; color: string; label: string }> = {
  SUCCESS:  { icon: CheckCircle,  color: "text-emerald-400", label: "Success" },
  FAILED:   { icon: XCircle,      color: "text-red-400",     label: "Failed"  },
  REJECTED: { icon: XCircle,      color: "text-orange-400",  label: "Rejected"},
  SKIPPED:  { icon: MinusCircle,  color: "text-zinc-500",    label: "Skipped" },
  DRY_RUN:  { icon: FlaskConical, color: "text-violet-400",  label: "Dry Run" },
};

function ActionItem({ action, index }: { action: ActionTaken; index: number }) {
  const { icon: Icon, color, label } = resultConfig[action.result] ?? resultConfig.SKIPPED;

  return (
    <div className="flex gap-3">
      <div className="flex flex-col items-center">
        <Icon className={clsx("h-4 w-4 shrink-0 mt-0.5", color)} />
        {/* connector line */}
        <div className="mt-1 w-px flex-1 bg-zinc-800" />
      </div>
      <div className="pb-4 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-mono font-medium text-zinc-200">{action.action}</span>
          <span className={clsx("text-xs", color)}>{label}</span>
          {action.duration_ms !== undefined && (
            <span className="text-xs text-zinc-600">{action.duration_ms}ms</span>
          )}
          <span className="text-xs text-zinc-600">#{index + 1}</span>
        </div>

        {Object.keys(action.params).length > 0 && (
          <pre className="mt-1.5 overflow-x-auto rounded bg-surface-2 p-2 text-xs text-zinc-400 font-mono">
            {JSON.stringify(action.params, null, 2)}
          </pre>
        )}

        {action.output !== null && action.output !== undefined && (
          <details className="mt-1">
            <summary className="cursor-pointer text-xs text-zinc-500 hover:text-zinc-300">
              output
            </summary>
            <pre className="mt-1 overflow-x-auto rounded bg-surface-2 p-2 text-xs text-zinc-400 font-mono">
              {typeof action.output === "string"
                ? action.output
                : JSON.stringify(action.output, null, 2)}
            </pre>
          </details>
        )}

        {action.timestamp && (
          <p className="mt-1 text-xs text-zinc-600">{formatTimestamp(action.timestamp)}</p>
        )}
      </div>
    </div>
  );
}

export function ActionsTimeline({ actions }: { actions: ActionTaken[] }) {
  if (!actions.length) return <p className="text-sm text-zinc-500">No actions taken.</p>;

  return (
    <div>
      {actions.map((a, i) => (
        <ActionItem key={i} action={a} index={i} />
      ))}
    </div>
  );
}
