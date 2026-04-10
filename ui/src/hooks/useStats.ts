import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export interface StatsData {
  total: number;
  resolved: number;
  escalated: number;
  failed: number;
  auto_resolution_rate: number;
  mttr_seconds: number | null;
  by_alert_name: Record<string, number>;
}

export function useStats() {
  return useQuery<StatsData>({
    queryKey: ["stats"],
    queryFn: ({ signal }) => api.get<StatsData>("/stats", signal),
    refetchInterval: 30_000,
    placeholderData: (prev) => prev,
  });
}
