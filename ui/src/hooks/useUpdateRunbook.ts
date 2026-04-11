import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

export function useUpdateRunbook(name: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (yaml: string) =>
      api.put<{ updated: string }>(`/runbooks/${encodeURIComponent(name)}`, { yaml }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["runbooks"] });
    },
  });
}
