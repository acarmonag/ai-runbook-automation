import { useStats } from "@/hooks/useStats";
import { Spinner } from "@/components/ui/Spinner";

function StatTile({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string | number;
  sub?: string;
  accent?: string;
}) {
  return (
    <div className="rounded-lg bg-zinc-800/60 border border-zinc-700/50 p-4 flex flex-col gap-1">
      <span className="text-xs text-zinc-500 uppercase tracking-wide">{label}</span>
      <span className={`text-2xl font-bold tabular-nums ${accent ?? "text-zinc-100"}`}>
        {value}
      </span>
      {sub && <span className="text-xs text-zinc-500">{sub}</span>}
    </div>
  );
}

function formatMttr(seconds: number | null): string {
  if (seconds === null) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  return `${(seconds / 3600).toFixed(1)}h`;
}

export function MttrDashboard() {
  const { data: stats, isLoading } = useStats();

  if (isLoading && !stats) {
    return (
      <div className="flex justify-center py-8">
        <Spinner className="h-5 w-5 text-zinc-500" />
      </div>
    );
  }

  if (!stats) return null;

  const pending = stats.total - stats.resolved - stats.escalated - stats.failed;

  // Sort by count descending, take top 5
  const topAlerts = Object.entries(stats.by_alert_name)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5);

  const maxCount = topAlerts[0]?.[1] ?? 1;

  return (
    <div className="space-y-6">
      {/* KPI grid */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatTile label="Total" value={stats.total} />
        <StatTile
          label="Auto-Resolved"
          value={`${stats.auto_resolution_rate}%`}
          sub={`${stats.resolved} incidents`}
          accent="text-emerald-400"
        />
        <StatTile
          label="MTTR"
          value={formatMttr(stats.mttr_seconds)}
          sub="mean time to resolve"
          accent="text-sky-400"
        />
        <StatTile
          label="Escalated"
          value={stats.escalated}
          sub={`${stats.failed} failed`}
          accent={stats.escalated > 0 ? "text-amber-400" : "text-zinc-400"}
        />
      </div>

      {/* Status breakdown bar */}
      {stats.total > 0 && (
        <div>
          <p className="text-xs text-zinc-500 mb-1.5">Outcome breakdown</p>
          <div className="flex h-3 w-full overflow-hidden rounded-full bg-zinc-800">
            {stats.resolved > 0 && (
              <div
                className="bg-emerald-500 h-full transition-all"
                style={{ width: `${(stats.resolved / stats.total) * 100}%` }}
                title={`Resolved: ${stats.resolved}`}
              />
            )}
            {stats.escalated > 0 && (
              <div
                className="bg-amber-500 h-full transition-all"
                style={{ width: `${(stats.escalated / stats.total) * 100}%` }}
                title={`Escalated: ${stats.escalated}`}
              />
            )}
            {stats.failed > 0 && (
              <div
                className="bg-red-600 h-full transition-all"
                style={{ width: `${(stats.failed / stats.total) * 100}%` }}
                title={`Failed: ${stats.failed}`}
              />
            )}
            {pending > 0 && (
              <div
                className="bg-zinc-600 h-full transition-all"
                style={{ width: `${(pending / stats.total) * 100}%` }}
                title={`Processing: ${pending}`}
              />
            )}
          </div>
          <div className="flex gap-3 mt-1.5">
            {[
              { label: "Resolved", color: "bg-emerald-500", count: stats.resolved },
              { label: "Escalated", color: "bg-amber-500", count: stats.escalated },
              { label: "Failed", color: "bg-red-600", count: stats.failed },
              { label: "Processing", color: "bg-zinc-600", count: pending },
            ]
              .filter((s) => s.count > 0)
              .map((s) => (
                <span key={s.label} className="flex items-center gap-1 text-xs text-zinc-500">
                  <span className={`inline-block h-2 w-2 rounded-full ${s.color}`} />
                  {s.label} ({s.count})
                </span>
              ))}
          </div>
        </div>
      )}

      {/* Top alert types */}
      {topAlerts.length > 0 && (
        <div>
          <p className="text-xs text-zinc-500 mb-2">Top alert types</p>
          <ul className="space-y-2">
            {topAlerts.map(([name, count]) => (
              <li key={name} className="flex items-center gap-2">
                <span className="text-xs text-zinc-400 w-40 truncate">{name}</span>
                <div className="flex-1 h-1.5 rounded-full bg-zinc-800 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-sky-500/70 transition-all"
                    style={{ width: `${(count / maxCount) * 100}%` }}
                  />
                </div>
                <span className="text-xs tabular-nums text-zinc-400 w-4 text-right">{count}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {stats.total === 0 && (
        <p className="text-sm text-zinc-600 text-center py-4">
          No incidents yet. Fire an alert to get started.
        </p>
      )}
    </div>
  );
}
