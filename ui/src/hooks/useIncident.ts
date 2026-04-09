import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Incident } from "@/types/incident";

export function useIncident(id: string) {
  return useQuery<Incident>({
    queryKey: ["incident", id],
    queryFn: ({ signal }) => api.get<Incident>(`/incidents/${id}`, signal),
    refetchInterval: 2_000,
    enabled: !!id,
    placeholderData: (prev) => prev,
  });
}
