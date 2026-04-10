import { useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { subscribe } from "@/hooks/useWebSocket";
import type { IncidentSummary } from "@/types/incident";

export function useIncidents() {
  const queryClient = useQueryClient();

  // Initial fetch + slow background refresh as a safety net.
  const query = useQuery<IncidentSummary[]>({
    queryKey: ["incidents"],
    queryFn: ({ signal }) => api.get<IncidentSummary[]>("/incidents", signal),
    refetchInterval: 30_000, // slow fallback — WS handles the fast path
    placeholderData: (prev) => prev,
  });

  // Real-time updates via WebSocket.
  useEffect(() => {
    return subscribe(() => {
      // Any incident update → re-fetch the list.
      queryClient.invalidateQueries({ queryKey: ["incidents"] });
    });
  }, [queryClient]);

  return query;
}
