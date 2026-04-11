import { useQuery } from "@tanstack/react-query";

export function useRunbookYaml(name: string, enabled: boolean) {
  return useQuery<string>({
    queryKey: ["runbook-yaml", name],
    queryFn: async ({ signal }) => {
      const res = await fetch(`/api/runbooks/${encodeURIComponent(name)}/yaml`, {
        signal,
      });
      if (!res.ok) throw new Error(`${res.status}`);
      return res.text();
    },
    enabled,
    staleTime: Infinity, // only refetch after a successful save
  });
}
