import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

export function useCreateRunbook() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (yaml: string) =>
      api.post<{ created: string }>("/runbooks", { yaml }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["runbooks"] });
    },
  });
}
