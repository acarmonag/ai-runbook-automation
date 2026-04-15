import { AlertTriangle, ShieldAlert, Wrench, FlaskConical, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { useApproveIncident } from "@/hooks/useApproveIncident";
import { useRejectIncident } from "@/hooks/useRejectIncident";

interface SreInsight {
  severity?: string;
  interpretation?: string;
  pattern?: string;
  next_step?: string;
  params?: Record<string, unknown>;
}

interface ApprovalBannerProps {
  incidentId: string;
  pendingAction: string;
  sreInsight?: SreInsight;
}

/** Friendly display name for action identifiers. */
function actionLabel(action: string): string {
  const labels: Record<string, string> = {
    restart_service:  "Restart Service",
    scale_service:    "Scale Service",
    escalate:         "Escalate Incident",
    run_diagnostic:   "Run Diagnostic",
  };
  return labels[action] ?? action.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Extract the params that are worth showing (skip internal/boring keys). */
function visibleParams(params: Record<string, unknown>): [string, string][] {
  const skip = new Set(["reason"]);
  return Object.entries(params)
    .filter(([k, v]) => !skip.has(k) && v !== undefined && v !== null && v !== "")
    .map(([k, v]) => [k.replace(/_/g, " "), String(v)]);
}

export function ApprovalBanner({ incidentId, pendingAction, sreInsight }: ApprovalBannerProps) {
  const approve = useApproveIncident();
  const reject  = useRejectIncident();

  const busy = approve.isPending || reject.isPending;

  const handleApprove = () =>
    approve.mutate({ incidentId, action: pendingAction, operator: "dashboard-user" });

  const handleReject = () =>
    reject.mutate({
      incidentId,
      action: pendingAction,
      reason: "Rejected by dashboard operator",
      operator: "dashboard-user",
    });

  const reason         = (sreInsight?.params?.reason ?? sreInsight?.next_step) as string | undefined;
  const interpretation = sreInsight?.interpretation;
  const pattern        = sreInsight?.pattern;
  // Don't repeat next_step in "Expected outcome" if it's already shown as the reason
  const nextStep       = sreInsight?.next_step !== reason ? sreInsight?.next_step : undefined;
  const params         = sreInsight?.params ? visibleParams(sreInsight.params) : [];

  return (
    <div className="mb-4 rounded-lg border border-amber-600/60 bg-amber-950/20 overflow-hidden">

      {/* ── Header bar ──────────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 bg-amber-900/30 px-4 py-2.5 border-b border-amber-700/40">
        <AlertTriangle className="h-4 w-4 shrink-0 text-amber-400" />
        <span className="text-sm font-semibold text-amber-300">Agent is waiting for your approval</span>
        <span className="ml-auto text-[11px] font-mono bg-amber-800/40 text-amber-300 px-2 py-0.5 rounded border border-amber-700/40">
          {actionLabel(pendingAction)}
        </span>
      </div>

      {/* ── Context body ────────────────────────────────────────────────── */}
      <div className="px-4 py-3 space-y-3">

        {/* Action params (service, replicas, etc.) */}
        {params.length > 0 && (
          <div className="flex flex-wrap gap-x-4 gap-y-1">
            {params.map(([k, v]) => (
              <span key={k} className="text-xs">
                <span className="text-zinc-500">{k}: </span>
                <span className="font-mono text-zinc-200">{v}</span>
              </span>
            ))}
          </div>
        )}

        {/* Why the agent wants to do this */}
        {reason && (
          <ContextRow
            icon={<ShieldAlert className="h-3.5 w-3.5 text-amber-400 mt-0.5 shrink-0" />}
            label="Why this is needed"
            text={reason}
            textClass="text-amber-200/90"
          />
        )}

        {/* What the agent found */}
        {interpretation && (
          <ContextRow
            icon={<FlaskConical className="h-3.5 w-3.5 text-zinc-400 mt-0.5 shrink-0" />}
            label="What the agent found"
            text={interpretation}
            textClass="text-zinc-300"
          />
        )}

        {/* Pattern identified */}
        {pattern && (
          <ContextRow
            icon={<Wrench className="h-3.5 w-3.5 text-zinc-500 mt-0.5 shrink-0" />}
            label="Identified pattern"
            text={pattern}
            textClass="text-zinc-400"
          />
        )}

        {/* Expected outcome */}
        {nextStep && (
          <ContextRow
            icon={<ArrowRight className="h-3.5 w-3.5 text-green-500 mt-0.5 shrink-0" />}
            label="Expected outcome"
            text={nextStep}
            textClass="text-green-400/80"
          />
        )}

        {/* Fallback when no context at all */}
        {!reason && !interpretation && !nextStep && (
          <p className="text-xs text-zinc-500 italic">No additional context from the agent.</p>
        )}
      </div>

      {/* ── Action buttons ───────────────────────────────────────────────── */}
      <div className="flex justify-end gap-2 px-4 py-3 border-t border-amber-700/30 bg-zinc-900/30">
        <Button variant="danger"  size="sm" onClick={handleReject}  disabled={busy}>
          {reject.isPending  ? <Spinner className="h-3 w-3" /> : null}
          Reject
        </Button>
        <Button variant="success" size="sm" onClick={handleApprove} disabled={busy}>
          {approve.isPending ? <Spinner className="h-3 w-3" /> : null}
          Approve
        </Button>
      </div>
    </div>
  );
}

// ── Small helper ──────────────────────────────────────────────────────────────

function ContextRow({
  icon,
  label,
  text,
  textClass,
}: {
  icon: React.ReactNode;
  label: string;
  text: string;
  textClass: string;
}) {
  return (
    <div className="flex gap-2">
      {icon}
      <div className="min-w-0">
        <span className="text-[10px] uppercase tracking-wider text-zinc-500 block mb-0.5">{label}</span>
        <p className={`text-xs leading-relaxed ${textClass}`}>{text}</p>
      </div>
    </div>
  );
}
