import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { WebhookResponse } from "@/types/incident";

export type Scenario =
  | "high_error_rate"
  | "high_latency"
  | "memory_leak"
  | "service_down"
  | "cpu_spike"
  | "database_connection_pool"
  | "network_latency"
  | "circuit_breaker_open"
  | "disk_pressure"
  | "service_degradation_scale"
  | "dependency_failure"
  | "high_traffic_load"
  | "cache_exhaustion"
  | "downstream_dependency"
  | "pod_crashloop";

// Pre-built Alertmanager payloads matching simulator/alert_generator.py
const SCENARIO_PAYLOADS: Record<Scenario, object> = {
  high_error_rate: {
    version: "4",
    status: "firing",
    receiver: "agent-webhook",
    groupLabels: { alertname: "HighErrorRate" },
    commonLabels: { alertname: "HighErrorRate", severity: "critical", service: "api" },
    commonAnnotations: { summary: "HTTP error rate above 15% for api" },
    groupKey: "{}:{alertname=\"HighErrorRate\"}",
    truncatedAlerts: 0,
    alerts: [{
      status: "firing",
      labels: { alertname: "HighErrorRate", severity: "critical", service: "api", environment: "production", team: "platform" },
      annotations: { summary: "HTTP error rate above 15% for api", description: "The api service is returning 5xx errors at 15.3% rate over the last 5 minutes. This is above the critical threshold of 10%. Affected endpoints: /api/users, /api/orders", value: "15.3%", threshold: "10%" },
      startsAt: new Date().toISOString(),
      endsAt: "0001-01-01T00:00:00Z",
      fingerprint: Math.random().toString(36).slice(2, 10),
    }],
  },
  high_latency: {
    version: "4",
    status: "firing",
    receiver: "agent-webhook",
    groupLabels: { alertname: "HighLatency" },
    commonLabels: { alertname: "HighLatency", severity: "warning", service: "api" },
    commonAnnotations: { summary: "p99 response latency exceeds 3 seconds for api" },
    groupKey: "{}:{alertname=\"HighLatency\"}",
    truncatedAlerts: 0,
    alerts: [{
      status: "firing",
      labels: { alertname: "HighLatency", severity: "warning", service: "api", environment: "production", team: "platform" },
      annotations: { summary: "p99 response latency exceeds 3 seconds for api", description: "The api p99 response latency has been above 3s for 10 minutes. Current p99: 4.2s, p95: 2.8s, p50: 0.8s. CPU utilization is at 87% suggesting resource saturation.", value: "4.2s", threshold: "3s" },
      startsAt: new Date().toISOString(),
      endsAt: "0001-01-01T00:00:00Z",
      fingerprint: Math.random().toString(36).slice(2, 10),
    }],
  },
  memory_leak: {
    version: "4",
    status: "firing",
    receiver: "agent-webhook",
    groupLabels: { alertname: "MemoryLeakDetected" },
    commonLabels: { alertname: "MemoryLeakDetected", severity: "warning", service: "worker" },
    commonAnnotations: { summary: "worker memory usage growing linearly — possible memory leak" },
    groupKey: "{}:{alertname=\"MemoryLeakDetected\"}",
    truncatedAlerts: 0,
    alerts: [{
      status: "firing",
      labels: { alertname: "MemoryLeakDetected", severity: "warning", service: "worker", environment: "production", team: "platform" },
      annotations: { summary: "worker memory usage growing linearly — possible memory leak", description: "worker memory usage has grown from 256MB to 1.8GB over the past hour and continues to grow at ~25MB/minute. Memory limit is 2GB. OOM kill expected within ~8 minutes.", current_mb: "1843", growth_rate: "25MB/min" },
      startsAt: new Date().toISOString(),
      endsAt: "0001-01-01T00:00:00Z",
      fingerprint: Math.random().toString(36).slice(2, 10),
    }],
  },
  service_down: {
    version: "4",
    status: "firing",
    receiver: "agent-webhook",
    groupLabels: { alertname: "ServiceDown" },
    commonLabels: { alertname: "ServiceDown", severity: "critical", service: "api" },
    commonAnnotations: { summary: "api is completely unreachable" },
    groupKey: "{}:{alertname=\"ServiceDown\"}",
    truncatedAlerts: 0,
    alerts: [{
      status: "firing",
      labels: { alertname: "ServiceDown", severity: "critical", service: "api", environment: "production", team: "platform" },
      annotations: { summary: "api is completely unreachable", description: "api health check has been failing for 3 consecutive checks (90 seconds). All instances are returning connection refused. Last successful health check: 3 minutes ago.", duration: "3m", last_seen: "3m ago" },
      startsAt: new Date().toISOString(),
      endsAt: "0001-01-01T00:00:00Z",
      fingerprint: Math.random().toString(36).slice(2, 10),
    }],
  },
  cpu_spike: {
    version: "4",
    status: "firing",
    receiver: "agent-webhook",
    groupLabels: { alertname: "HighCPU" },
    commonLabels: { alertname: "HighCPU", severity: "warning", service: "api" },
    commonAnnotations: { summary: "api CPU usage at 94% — possible CPU saturation" },
    groupKey: "{}:{alertname=\"HighCPU\"}",
    truncatedAlerts: 0,
    alerts: [{
      status: "firing",
      labels: { alertname: "HighCPU", severity: "warning", service: "api", environment: "production", team: "platform" },
      annotations: { summary: "api CPU usage at 94% — possible CPU saturation", description: "api CPU usage has been above 90% for 15 minutes. CPU throttling is occurring. Request queue is backing up. Current load: 450 req/s, normal: 200 req/s", value: "94%", threshold: "90%", duration: "15m" },
      startsAt: new Date().toISOString(),
      endsAt: "0001-01-01T00:00:00Z",
      fingerprint: Math.random().toString(36).slice(2, 10),
    }],
  },
  database_connection_pool: {
    version: "4",
    status: "firing",
    receiver: "agent-webhook",
    groupLabels: { alertname: "DatabaseConnectionPoolExhausted" },
    commonLabels: { alertname: "DatabaseConnectionPoolExhausted", severity: "critical", service: "api" },
    commonAnnotations: { summary: "Database connection pool exhausted — requests timing out" },
    groupKey: "{}:{alertname=\"DatabaseConnectionPoolExhausted\"}",
    truncatedAlerts: 0,
    alerts: [{
      status: "firing",
      labels: { alertname: "DatabaseConnectionPoolExhausted", severity: "critical", service: "api", environment: "production", team: "platform" },
      annotations: { summary: "Database connection pool exhausted", description: "HikariPool connection pool is exhausted (pool_size=100, waiting=47). Queries timing out after 5000ms. 12% of requests returning 500.", pool_used: "100", pool_waiting: "47", timeout_ms: "5000" },
      startsAt: new Date().toISOString(),
      endsAt: "0001-01-01T00:00:00Z",
      fingerprint: Math.random().toString(36).slice(2, 10),
    }],
  },
  network_latency: {
    version: "4",
    status: "firing",
    receiver: "agent-webhook",
    groupLabels: { alertname: "HighNetworkLatency" },
    commonLabels: { alertname: "HighNetworkLatency", severity: "warning", service: "api" },
    commonAnnotations: { summary: "Inter-service p99 latency exceeds 5s SLO" },
    groupKey: "{}:{alertname=\"HighNetworkLatency\"}",
    truncatedAlerts: 0,
    alerts: [{
      status: "firing",
      labels: { alertname: "HighNetworkLatency", severity: "warning", service: "api", environment: "production", team: "platform" },
      annotations: { summary: "Inter-service p99 latency exceeds 5s SLO", description: "p99 latency between api and payment-service has been above 5s for 10 minutes. Packet loss detected on eth0: 12%. Downstream timeouts increasing.", p99_ms: "6400", slo_ms: "500", packet_loss: "12%" },
      startsAt: new Date().toISOString(),
      endsAt: "0001-01-01T00:00:00Z",
      fingerprint: Math.random().toString(36).slice(2, 10),
    }],
  },
  circuit_breaker_open: {
    version: "4",
    status: "firing",
    receiver: "agent-webhook",
    groupLabels: { alertname: "CircuitBreakerOpen" },
    commonLabels: { alertname: "CircuitBreakerOpen", severity: "critical", service: "api" },
    commonAnnotations: { summary: "Circuit breaker OPEN for inventory-service" },
    groupKey: "{}:{alertname=\"CircuitBreakerOpen\"}",
    truncatedAlerts: 0,
    alerts: [{
      status: "firing",
      labels: { alertname: "CircuitBreakerOpen", severity: "critical", service: "api", environment: "production", team: "platform" },
      annotations: { summary: "Circuit breaker OPEN for inventory-service", description: "Circuit breaker for inventory-service tripped OPEN after error rate exceeded 50%. All inventory calls failing fast. 45% of checkout requests affected.", dependency: "inventory-service", error_rate: "50%", affected_requests: "45%" },
      startsAt: new Date().toISOString(),
      endsAt: "0001-01-01T00:00:00Z",
      fingerprint: Math.random().toString(36).slice(2, 10),
    }],
  },
  disk_pressure: {
    version: "4",
    status: "firing",
    receiver: "agent-webhook",
    groupLabels: { alertname: "DiskPressure" },
    commonLabels: { alertname: "DiskPressure", severity: "warning", service: "api" },
    commonAnnotations: { summary: "Disk usage at 93% on /var/log — write failures imminent" },
    groupKey: "{}:{alertname=\"DiskPressure\"}",
    truncatedAlerts: 0,
    alerts: [{
      status: "firing",
      labels: { alertname: "DiskPressure", severity: "warning", service: "api", environment: "production", team: "platform" },
      annotations: { summary: "Disk usage at 93% — write failures imminent", description: "Disk usage on /var/log has reached 93%. ENOSPC errors appearing in logs. Core dump found consuming 2.1GB. Log rotation overdue.", disk_usage: "93%", threshold: "85%", free_gb: "7" },
      startsAt: new Date().toISOString(),
      endsAt: "0001-01-01T00:00:00Z",
      fingerprint: Math.random().toString(36).slice(2, 10),
    }],
  },
  service_degradation_scale: {
    version: "4",
    status: "firing",
    receiver: "agent-webhook",
    groupLabels: { alertname: "ServiceDegraded" },
    commonLabels: { alertname: "ServiceDegraded", severity: "warning", service: "api" },
    commonAnnotations: { summary: "api degraded under traffic spike — scale-out needed" },
    groupKey: "{}:{alertname=\"ServiceDegraded\"}",
    truncatedAlerts: 0,
    alerts: [{
      status: "firing",
      labels: { alertname: "ServiceDegraded", severity: "warning", service: "api", environment: "production", team: "platform" },
      annotations: { summary: "api degraded under traffic spike", description: "api is receiving 900 req/s (3x baseline). All 3 replicas saturated at 88% CPU. HPA throttled at max replicas=3. 7% of requests returning 503.", request_rate: "900/s", replicas: "3", cpu: "88%", error_rate: "7%" },
      startsAt: new Date().toISOString(),
      endsAt: "0001-01-01T00:00:00Z",
      fingerprint: Math.random().toString(36).slice(2, 10),
    }],
  },
  dependency_failure: {
    version: "4",
    status: "firing",
    receiver: "agent-webhook",
    groupLabels: { alertname: "DependencyDown" },
    commonLabels: { alertname: "DependencyDown", severity: "critical", service: "api" },
    commonAnnotations: { summary: "payment-service completely unreachable — 98% checkout failure" },
    groupKey: "{}:{alertname=\"DependencyDown\"}",
    truncatedAlerts: 0,
    alerts: [{
      status: "firing",
      labels: { alertname: "DependencyDown", severity: "critical", service: "api", environment: "production", team: "platform", instance: "payment-service:8082" },
      annotations: { summary: "payment-service completely unreachable", description: "payment-service is returning ECONNREFUSED on all endpoints. 98% of checkout requests failing. Circuit breaker OPEN. Fallback payment processor also unavailable.", dependency: "payment-service", error_rate: "98%", duration: "5m" },
      startsAt: new Date().toISOString(),
      endsAt: "0001-01-01T00:00:00Z",
      fingerprint: Math.random().toString(36).slice(2, 10),
    }],
  },
  high_traffic_load: {
    version: "4",
    status: "firing",
    receiver: "agent-webhook",
    groupLabels: { alertname: "HighTrafficLoad" },
    commonLabels: { alertname: "HighTrafficLoad", severity: "warning", service: "api" },
    commonAnnotations: { summary: "Traffic spike — api receiving 4x baseline RPS, latency degrading" },
    groupKey: "{}:{alertname=\"HighTrafficLoad\"}",
    truncatedAlerts: 0,
    alerts: [{
      status: "firing",
      labels: { alertname: "HighTrafficLoad", severity: "warning", service: "api", environment: "production", team: "platform" },
      annotations: { summary: "Traffic spike: api receiving 1200 req/s (4x baseline)", description: "api is receiving 1200 req/s, 4x the normal baseline of 300 req/s. p99 latency is 4.8s. CPU at 91% on all replicas. Scale out required — do NOT restart, the service is healthy.", request_rate: "1200/s", baseline: "300/s", p99_latency: "4.8s", cpu: "91%" },
      startsAt: new Date().toISOString(),
      endsAt: "0001-01-01T00:00:00Z",
      fingerprint: Math.random().toString(36).slice(2, 10),
    }],
  },
  cache_exhaustion: {
    version: "4",
    status: "firing",
    receiver: "agent-webhook",
    groupLabels: { alertname: "CacheExhaustion" },
    commonLabels: { alertname: "CacheExhaustion", severity: "warning", service: "api" },
    commonAnnotations: { summary: "Cache hit rate at 18% — Redis memory near limit, latency spiking" },
    groupKey: "{}:{alertname=\"CacheExhaustion\"}",
    truncatedAlerts: 0,
    alerts: [{
      status: "firing",
      labels: { alertname: "CacheExhaustion", severity: "warning", service: "api", environment: "production", team: "platform" },
      annotations: { summary: "Cache hit rate collapsed to 18% — Redis memory at 95%", description: "Redis memory usage is at 1.9GB of 2GB limit. Cache hit rate dropped from 94% to 18%. evicted_keys increasing at 2000/min. p99 latency spiked to 3.2s due to cache misses hitting the database.", hit_rate: "18%", redis_memory: "1.9GB/2GB", evicted_keys: "2000/min" },
      startsAt: new Date().toISOString(),
      endsAt: "0001-01-01T00:00:00Z",
      fingerprint: Math.random().toString(36).slice(2, 10),
    }],
  },
  downstream_dependency: {
    version: "4",
    status: "firing",
    receiver: "agent-webhook",
    groupLabels: { alertname: "DownstreamFailure" },
    commonLabels: { alertname: "DownstreamFailure", severity: "critical", service: "api" },
    commonAnnotations: { summary: "inventory-service unreachable — circuit breaker OPEN" },
    groupKey: "{}:{alertname=\"DownstreamFailure\"}",
    truncatedAlerts: 0,
    alerts: [{
      status: "firing",
      labels: { alertname: "DownstreamFailure", severity: "critical", service: "api", environment: "production", team: "platform", instance: "inventory-service:8081" },
      annotations: { summary: "inventory-service unreachable, circuit breaker OPEN", description: "inventory-service is returning ECONNREFUSED. Circuit breaker OPEN after 50% error rate threshold exceeded. 62% of product-page requests failing. Restarting api will not help — the dependency is the problem.", dependency: "inventory-service", error_rate: "62%", circuit_breaker: "OPEN" },
      startsAt: new Date().toISOString(),
      endsAt: "0001-01-01T00:00:00Z",
      fingerprint: Math.random().toString(36).slice(2, 10),
    }],
  },
  pod_crashloop: {
    version: "4",
    status: "firing",
    receiver: "agent-webhook",
    groupLabels: { alertname: "PodCrashLoop" },
    commonLabels: { alertname: "PodCrashLoop", severity: "critical", service: "api" },
    commonAnnotations: { summary: "api pod in CrashLoopBackOff — OOMKilled 7 times in 10 minutes" },
    groupKey: "{}:{alertname=\"PodCrashLoop\"}",
    truncatedAlerts: 0,
    alerts: [{
      status: "firing",
      labels: { alertname: "PodCrashLoop", severity: "critical", service: "api", environment: "production", team: "platform" },
      annotations: { summary: "api CrashLoopBackOff: OOMKilled 7 times in 10 minutes", description: "api container is being OOMKilled repeatedly. Memory usage reaches 2040MB (limit: 2048MB) before each kill. Growing at 80MB/min — possible memory leak. Scale UP replicas to maintain availability while investigating.", restarts: "7", exit_reason: "OOMKilled", memory_limit: "2048MB", memory_at_kill: "2040MB" },
      startsAt: new Date().toISOString(),
      endsAt: "0001-01-01T00:00:00Z",
      fingerprint: Math.random().toString(36).slice(2, 10),
    }],
  },
};

interface FireAlertPayload {
  scenario: Scenario;
}

export function useFireAlert() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: async ({ scenario }: FireAlertPayload) => {
      // Switch the mock Prometheus scenario before firing so metrics/logs match.
      try {
        await api.post("/simulator/scenario", { scenario });
      } catch {
        // Non-fatal — best effort. The scenario may already be set correctly.
      }
      const payload = SCENARIO_PAYLOADS[scenario];
      return api.post<WebhookResponse>("/alerts/webhook", payload);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["incidents"] });
    },
  });
}
