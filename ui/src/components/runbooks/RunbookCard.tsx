import type { Runbook } from "@/types/runbook";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";

export function RunbookCard({ runbook }: { runbook: Runbook }) {
  return (
    <Card>
      <div className="mb-2 flex items-start justify-between gap-2">
        <h3 className="font-mono text-sm font-semibold text-zinc-100">{runbook.name}</h3>
        <div className="flex flex-wrap gap-1">
          {runbook.metadata?.severity && (
            <Badge className="bg-zinc-800 text-zinc-400 text-xs">
              {runbook.metadata.severity}
            </Badge>
          )}
          {runbook.metadata?.team && (
            <Badge className="bg-zinc-800 text-zinc-400 text-xs">
              {runbook.metadata.team}
            </Badge>
          )}
        </div>
      </div>

      <p className="mb-3 text-xs text-zinc-500 leading-relaxed">{runbook.description}</p>

      <div className="mb-3">
        <p className="mb-1 text-xs font-medium text-zinc-400">Triggers</p>
        <div className="flex flex-wrap gap-1">
          {runbook.triggers.map((t) => (
            <Badge key={t} className="bg-amber-900/40 text-amber-300 border border-amber-800/50">
              {t}
            </Badge>
          ))}
        </div>
      </div>

      {runbook.actions && runbook.actions.length > 0 && (
        <div className="mb-3">
          <p className="mb-1 text-xs font-medium text-zinc-400">
            Actions ({runbook.actions.length})
          </p>
          <ol className="flex flex-col gap-1">
            {runbook.actions.map((a, i) => (
              <li key={i} className="flex gap-2 text-xs text-zinc-500">
                <span className="shrink-0 text-zinc-600">{i + 1}.</span>
                <span>{a}</span>
              </li>
            ))}
          </ol>
        </div>
      )}

      {runbook.action_count !== undefined && !runbook.actions && (
        <p className="text-xs text-zinc-600">{runbook.action_count} actions defined</p>
      )}

      {runbook.escalation_threshold && (
        <div className="mt-2 rounded bg-surface-2 px-3 py-2">
          <p className="mb-0.5 text-xs font-medium text-zinc-400">Escalation</p>
          <p className="text-xs text-zinc-500">{runbook.escalation_threshold}</p>
        </div>
      )}
    </Card>
  );
}
