import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

export type AgentMode = "AUTO" | "MANUAL" | "DRY_RUN";

interface ModeResponse {
  mode: AgentMode;
}

export function useAgentMode() {
  const queryClient = useQueryClient();

  const query = useQuery<ModeResponse>({
    queryKey: ["agent-mode"],
    queryFn: ({ signal }) => api.get<ModeResponse>("/agent/mode", signal),
    refetchInterval: 10_000,
    placeholderData: (prev) => prev,
  });

  const mutation = useMutation({
    mutationFn: (mode: AgentMode) =>
      api.post<ModeResponse>("/agent/mode", { mode }),
    onSuccess: (data) => {
      queryClient.setQueryData(["agent-mode"], data);
    },
  });

  return {
    mode: query.data?.mode ?? "AUTO",
    isLoading: query.isLoading,
    isSwitching: mutation.isPending,
    setMode: mutation.mutate,
    error: mutation.error,
  };
}
