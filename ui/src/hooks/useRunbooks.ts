import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Runbook } from "@/types/runbook";

export function useRunbooks() {
  return useQuery<Runbook[]>({
    queryKey: ["runbooks"],
    queryFn: ({ signal }) => api.get<Runbook[]>("/runbooks", signal),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });
}
