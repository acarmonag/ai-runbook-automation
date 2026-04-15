import { useParams, Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { useIncident } from "@/hooks/useIncident";
import { StatusBadge } from "@/components/incidents/StatusBadge";
import { ActionsTimeline } from "@/components/incidents/ActionsTimeline";
import { ReasoningTranscript } from "@/components/incidents/ReasoningTranscript";
import { ApprovalBanner } from "@/components/incidents/ApprovalBanner";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { PirPanel } from "@/components/incidents/PirPanel";
import { formatDuration, formatTimestamp } from "@/lib/format";

export function IncidentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { data: incident, isLoading } = useIncident(id ?? "");

  if (isLoading && !incident) {
    return (
      <div className="flex justify-center py-16">
        <Spinner className="h-6 w-6 text-zinc-500" />
      </div>
    );
  }

  if (!incident) {
    return <p className="text-sm text-zinc-500">Incident not found.</p>;
  }

  const alertLabels = (incident.alert?.labels ?? {}) as Record<string, string>;

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      {/* Back + header */}
      <div className="flex items-start gap-3">
        <Link
          to="/"
          className="mt-0.5 text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <div className="flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="text-lg font-semibold text-zinc-100">{incident.alert_name}</h1>
            <StatusBadge status={incident.status} />
          </div>
          <p className="text-xs text-zinc-500 mt-0.5">
            {incident.incident_id} · started {formatTimestamp(incident.started_at)}
            {incident.resolved_at && ` · resolved ${formatTimestamp(incident.resolved_at)}`}
            {" · "}duration {formatDuration(incident.started_at, incident.resolved_at)}
          </p>
        </div>
      </div>

      {/* Approval gate */}
      {incident.pending_action && incident.approval_state === "PENDING" && (
        <ApprovalBanner
          incidentId={incident.incident_id}
          pendingAction={incident.pending_action}
          sreInsight={incident.sre_insight}
        />
      )}

      {/* Alert info */}
      {Object.keys(alertLabels).length > 0 && (
        <Card title="Alert Labels">
          <div className="flex flex-wrap gap-2">
            {Object.entries(alertLabels).map(([k, v]) => (
              <span key={k} className="inline-flex gap-1 text-xs">
                <span className="text-zinc-500">{k}=</span>
                <span className="font-mono text-zinc-300">{v}</span>
              </span>
            ))}
          </div>
        </Card>
      )}

      {/* Summary + root cause */}
      {(incident.summary ?? incident.root_cause) && (
        <Card title="Analysis">
          {incident.summary && (
            <p className="text-sm text-zinc-300 mb-2">{incident.summary}</p>
          )}
          {incident.root_cause && (
            <>
              <p className="text-xs font-medium text-zinc-400 mb-1">Root Cause</p>
              <p className="text-sm text-zinc-400">{incident.root_cause}</p>
            </>
          )}
        </Card>
      )}

      {/* Actions */}
      <Card title={`Actions (${incident.actions_taken.length})`}>
        <ActionsTimeline actions={incident.actions_taken} />
      </Card>

      {/* Recommendations */}
      {incident.recommendations.length > 0 && (
        <Card title="Recommendations">
          <ul className="flex flex-col gap-1.5">
            {incident.recommendations.map((r, i) => (
              <li key={i} className="flex gap-2 text-sm text-zinc-400">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-zinc-600" />
                <span>{r}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {/* Reasoning transcript */}
      <Card title={`Reasoning Transcript (${incident.reasoning_transcript.length} messages)`}>
        <ReasoningTranscript messages={incident.reasoning_transcript} />
      </Card>

      {/* Post-Incident Review */}
      {incident.pir && (
        <Card title="Post-Incident Review">
          <PirPanel pir={incident.pir} />
        </Card>
      )}
      {!incident.pir && ["RESOLVED", "ESCALATED", "FAILED"].includes(incident.status) && (
        <Card title="Post-Incident Review">
          <p className="text-sm text-zinc-500 italic">Generating PIR… refresh in a moment.</p>
        </Card>
      )}
    </div>
  );
}
