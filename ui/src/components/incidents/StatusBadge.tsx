import { clsx } from "clsx";
import type { IncidentStatus } from "@/types/incident";

const config: Record<IncidentStatus, { label: string; className: string }> = {
  DETECTED:   { label: "Detected",   className: "bg-blue-900/50 text-blue-300 border border-blue-700" },
  OBSERVING:  { label: "Observing",  className: "bg-cyan-900/50 text-cyan-300 border border-cyan-700" },
  REASONING:  { label: "Reasoning",  className: "bg-violet-900/50 text-violet-300 border border-violet-700" },
  ACTING:     { label: "Acting",     className: "bg-amber-900/50 text-amber-300 border border-amber-700" },
  VERIFYING:  { label: "Verifying",  className: "bg-indigo-900/50 text-indigo-300 border border-indigo-700" },
  PENDING:            { label: "Pending",          className: "bg-zinc-800 text-zinc-400 border border-zinc-700" },
  PENDING_APPROVAL:   { label: "Awaiting Approval", className: "animate-pulse bg-amber-900/60 text-amber-300 border border-amber-500" },
  PROCESSING: { label: "Processing", className: "bg-amber-900/50 text-amber-300 border border-amber-700" },
  RESOLVED:   { label: "Resolved",   className: "bg-emerald-900/50 text-emerald-300 border border-emerald-700" },
  ESCALATED:  { label: "Escalated",  className: "bg-orange-900/50 text-orange-300 border border-orange-700" },
  FAILED:     { label: "Failed",     className: "bg-red-900/50 text-red-300 border border-red-700" },
};

interface StatusBadgeProps {
  status: IncidentStatus;
}

export function StatusBadge({ status }: StatusBadgeProps) {
  const { label, className } = config[status] ?? config.PENDING;
  return (
    <span className={clsx("inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium", className)}>
      {label}
    </span>
  );
}
