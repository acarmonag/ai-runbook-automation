import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

interface ApprovePayload {
  incidentId: string;
  action: string;
  operator?: string;
}

export function useApproveIncident() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: ({ incidentId, action, operator }: ApprovePayload) =>
      api.post(`/incidents/${incidentId}/approve`, { action, operator }),
    onSettled: (_data, _err, { incidentId }) => {
      void qc.invalidateQueries({ queryKey: ["incident", incidentId] });
      void qc.invalidateQueries({ queryKey: ["incidents"] });
    },
  });
}
