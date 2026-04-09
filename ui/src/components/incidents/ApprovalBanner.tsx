import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { useApproveIncident } from "@/hooks/useApproveIncident";
import { useRejectIncident } from "@/hooks/useRejectIncident";

interface ApprovalBannerProps {
  incidentId: string;
  pendingAction: string;
}

export function ApprovalBanner({ incidentId, pendingAction }: ApprovalBannerProps) {
  const approve = useApproveIncident();
  const reject = useRejectIncident();

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

  return (
    <div className="mb-4 flex items-center gap-3 rounded-lg border border-amber-700 bg-amber-950/30 px-4 py-3">
      <AlertTriangle className="h-4 w-4 shrink-0 text-amber-400" />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-amber-300">Approval required</p>
        <p className="text-xs text-amber-400/70 font-mono">{pendingAction}</p>
      </div>
      <div className="flex gap-2">
        <Button
          variant="success"
          size="sm"
          onClick={handleApprove}
          disabled={busy}
        >
          {approve.isPending ? <Spinner className="h-3 w-3" /> : null}
          Approve
        </Button>
        <Button
          variant="danger"
          size="sm"
          onClick={handleReject}
          disabled={busy}
        >
          {reject.isPending ? <Spinner className="h-3 w-3" /> : null}
          Reject
        </Button>
      </div>
    </div>
  );
}
