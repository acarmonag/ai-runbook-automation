import { useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { subscribe } from "@/hooks/useWebSocket";
import type { Incident } from "@/types/incident";

export function useIncident(id: string) {
  const queryClient = useQueryClient();

  const query = useQuery<Incident>({
    queryKey: ["incident", id],
    queryFn: ({ signal }) => api.get<Incident>(`/incidents/${id}`, signal),
    refetchInterval: 30_000, // slow fallback — WS handles the fast path
    enabled: !!id,
    placeholderData: (prev) => prev,
  });

  // Real-time updates via WebSocket — only refetch when this incident changes.
  useEffect(() => {
    if (!id) return;
    return subscribe((data) => {
      const msg = data as { incident_id?: string };
      if (msg.incident_id === id) {
        queryClient.invalidateQueries({ queryKey: ["incident", id] });
      }
    });
  }, [id, queryClient]);

  return query;
}
