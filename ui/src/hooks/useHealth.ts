import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { HealthStatus } from "@/types/health";

export function useHealth() {
  return useQuery<HealthStatus>({
    queryKey: ["health"],
    queryFn: ({ signal }) => api.get<HealthStatus>("/health", signal),
    refetchInterval: 5_000,
    placeholderData: (prev) => prev,
  });
}
