export interface Runbook {
  name: string;
  description: string;
  triggers: string[];
  action_count?: number;
  actions?: string[];
  escalation_threshold: string;
  metadata?: {
    severity?: string;
    team?: string;
    runbook_version?: string;
  };
}
