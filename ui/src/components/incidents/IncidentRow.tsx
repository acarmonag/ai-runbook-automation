import { Link } from "react-router-dom";
import { formatDuration, formatRelative } from "@/lib/format";
import { StatusBadge } from "./StatusBadge";
import type { IncidentSummary } from "@/types/incident";

interface IncidentRowProps {
  incident: IncidentSummary;
}

export function IncidentRow({ incident }: IncidentRowProps) {
  const isActive = !["RESOLVED", "ESCALATED", "FAILED"].includes(incident.status);
  const needsApproval = incident.status === "PENDING_APPROVAL";

  return (
    <Link
      to={`/incidents/${incident.incident_id}`}
      className={`flex items-center gap-3 border-b border-zinc-800/60 px-4 py-3 transition-colors hover:bg-zinc-800/30 ${needsApproval ? "bg-amber-950/20" : ""}`}
    >
      <StatusBadge status={incident.status} />
      {needsApproval && (
        <span className="relative flex h-2 w-2 shrink-0">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400 opacity-75" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-amber-500" />
        </span>
      )}

      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-zinc-100">{incident.alert_name}</p>
        {incident.summary && (
          <p className="truncate text-xs text-zinc-500">{incident.summary}</p>
        )}
      </div>

      <div className="flex shrink-0 flex-col items-end gap-0.5 text-right">
        <span className="text-xs text-zinc-500">
          {incident.actions_taken_count} action{incident.actions_taken_count !== 1 ? "s" : ""}
        </span>
        <span className="text-xs text-zinc-600">
          {isActive
            ? formatDuration(incident.started_at)
            : formatRelative(incident.resolved_at ?? incident.started_at)}
        </span>
      </div>
    </Link>
  );
}
