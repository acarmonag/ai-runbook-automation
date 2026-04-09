import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { IncidentSummary } from "@/types/incident";

export function useIncidents() {
  return useQuery<IncidentSummary[]>({
    queryKey: ["incidents"],
    queryFn: ({ signal }) => api.get<IncidentSummary[]>("/incidents", signal),
    refetchInterval: 2_000,
    placeholderData: (prev) => prev,
  });
}
