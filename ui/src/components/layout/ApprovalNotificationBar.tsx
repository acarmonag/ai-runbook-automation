/**
 * Global approval notification bar.
 *
 * Queries the incident list for any PENDING_APPROVAL incidents and shows
 * a sticky amber banner with a direct link to approve/reject.
 * Sits below the TopBar so it's visible on every page.
 */

import { Link } from "react-router-dom";
import { AlertTriangle } from "lucide-react";
import { useIncidents } from "@/hooks/useIncidents";

export function ApprovalNotificationBar() {
  const { data: incidents } = useIncidents();

  const pending = (incidents ?? []).filter(
    (inc) => inc.status === "PENDING_APPROVAL",
  );

  if (pending.length === 0) return null;

  return (
    <div className="flex items-center gap-2 bg-amber-900/50 border-b border-amber-700/60 px-4 py-2 animate-pulse">
      <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-amber-400" />
      <span className="text-xs font-semibold text-amber-300">
        {pending.length === 1
          ? "Agent is waiting for your approval"
          : `${pending.length} agents waiting for approval`}
      </span>
      <div className="ml-2 flex flex-wrap gap-2">
        {pending.map((inc) => (
          <Link
            key={inc.incident_id}
            to={`/incidents/${inc.incident_id}`}
            className="rounded border border-amber-600/60 bg-amber-950/60 px-2 py-0.5 text-[11px] font-mono text-amber-300 hover:bg-amber-900/60 transition-colors"
          >
            {inc.alert_name} · {inc.incident_id}
          </Link>
        ))}
      </div>
    </div>
  );
}
