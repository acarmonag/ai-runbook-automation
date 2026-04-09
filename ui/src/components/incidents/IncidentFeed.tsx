import { useIncidents } from "@/hooks/useIncidents";
import { IncidentRow } from "./IncidentRow";
import { EmptyState } from "@/components/ui/EmptyState";
import { Spinner } from "@/components/ui/Spinner";

export function IncidentFeed() {
  const { data: incidents, isLoading, isError } = useIncidents();

  if (isLoading && !incidents) {
    return (
      <div className="flex justify-center py-10">
        <Spinner className="h-6 w-6 text-zinc-500" />
      </div>
    );
  }

  if (isError) {
    return (
      <EmptyState
        title="Cannot reach API"
        description="Make sure the agent is running: make up"
      />
    );
  }

  if (!incidents?.length) {
    return (
      <EmptyState
        title="No incidents yet"
        description="Fire an alert from the simulator to get started."
      />
    );
  }

  const sorted = [...incidents].sort(
    (a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime(),
  );

  return (
    <div className="flex flex-col divide-y divide-transparent">
      {sorted.map((inc) => (
        <IncidentRow key={inc.incident_id} incident={inc} />
      ))}
    </div>
  );
}
