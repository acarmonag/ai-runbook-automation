export interface HealthStatus {
  status: "healthy" | "degraded" | "unhealthy";
  claude_api: "reachable" | "unreachable";
  prometheus: "reachable" | "unreachable";
  queue_depth: number;
  active_workers: number;
  incidents_processed: number;
}
