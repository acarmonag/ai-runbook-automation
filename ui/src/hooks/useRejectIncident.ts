import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

interface RejectPayload {
  incidentId: string;
  action: string;
  reason?: string;
  operator?: string;
}

export function useRejectIncident() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: ({ incidentId, action, reason, operator }: RejectPayload) =>
      api.post(`/incidents/${incidentId}/reject`, { action, reason, operator }),
    onSettled: (_data, _err, { incidentId }) => {
      void qc.invalidateQueries({ queryKey: ["incident", incidentId] });
      void qc.invalidateQueries({ queryKey: ["incidents"] });
    },
  });
}
