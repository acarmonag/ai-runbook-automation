import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { WebhookResponse } from "@/types/incident";

export type Scenario =
  | "high_error_rate"
  | "high_latency"
  | "memory_leak"
  | "service_down"
  | "cpu_spike";

// Pre-built Alertmanager payloads matching simulator/alert_generator.py
const SCENARIO_PAYLOADS: Record<Scenario, object> = {
  high_error_rate: {
    version: "4",
    status: "firing",
    receiver: "agent-webhook",
    groupLabels: { alertname: "HighErrorRate" },
    commonLabels: { alertname: "HighErrorRate", severity: "critical", service: "api-service" },
    commonAnnotations: { summary: "HTTP error rate above 15% for api-service" },
    groupKey: "{}:{alertname=\"HighErrorRate\"}",
    truncatedAlerts: 0,
    alerts: [{
      status: "firing",
      labels: { alertname: "HighErrorRate", severity: "critical", service: "api-service", environment: "production", team: "platform" },
      annotations: { summary: "HTTP error rate above 15% for api-service", description: "The api-service is returning 5xx errors at 15.3% rate over the last 5 minutes. This is above the critical threshold of 10%. Affected endpoints: /api/users, /api/orders", value: "15.3%", threshold: "10%" },
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
    commonLabels: { alertname: "HighLatency", severity: "warning", service: "api-service" },
    commonAnnotations: { summary: "p99 response latency exceeds 3 seconds for api-service" },
    groupKey: "{}:{alertname=\"HighLatency\"}",
    truncatedAlerts: 0,
    alerts: [{
      status: "firing",
      labels: { alertname: "HighLatency", severity: "warning", service: "api-service", environment: "production", team: "platform" },
      annotations: { summary: "p99 response latency exceeds 3 seconds for api-service", description: "The api-service p99 response latency has been above 3s for 10 minutes. Current p99: 4.2s, p95: 2.8s, p50: 0.8s. CPU utilization is at 87% suggesting resource saturation.", value: "4.2s", threshold: "3s" },
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
    commonLabels: { alertname: "MemoryLeakDetected", severity: "warning", service: "worker-service" },
    commonAnnotations: { summary: "worker-service memory usage growing linearly — possible memory leak" },
    groupKey: "{}:{alertname=\"MemoryLeakDetected\"}",
    truncatedAlerts: 0,
    alerts: [{
      status: "firing",
      labels: { alertname: "MemoryLeakDetected", severity: "warning", service: "worker-service", environment: "production", team: "platform" },
      annotations: { summary: "worker-service memory usage growing linearly — possible memory leak", description: "worker-service memory usage has grown from 256MB to 1.8GB over the past hour and continues to grow at ~25MB/minute. Memory limit is 2GB. OOM kill expected within ~8 minutes.", current_mb: "1843", growth_rate: "25MB/min" },
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
    commonLabels: { alertname: "ServiceDown", severity: "critical", service: "api-service" },
    commonAnnotations: { summary: "api-service is completely unreachable" },
    groupKey: "{}:{alertname=\"ServiceDown\"}",
    truncatedAlerts: 0,
    alerts: [{
      status: "firing",
      labels: { alertname: "ServiceDown", severity: "critical", service: "api-service", environment: "production", team: "platform" },
      annotations: { summary: "api-service is completely unreachable", description: "api-service health check has been failing for 3 consecutive checks (90 seconds). All instances are returning connection refused. Last successful health check: 3 minutes ago.", duration: "3m", last_seen: "3m ago" },
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
    commonLabels: { alertname: "HighCPU", severity: "warning", service: "api-service" },
    commonAnnotations: { summary: "api-service CPU usage at 94% — possible CPU saturation" },
    groupKey: "{}:{alertname=\"HighCPU\"}",
    truncatedAlerts: 0,
    alerts: [{
      status: "firing",
      labels: { alertname: "HighCPU", severity: "warning", service: "api-service", environment: "production", team: "platform" },
      annotations: { summary: "api-service CPU usage at 94% — possible CPU saturation", description: "api-service CPU usage has been above 90% for 15 minutes. CPU throttling is occurring. Request queue is backing up. Current load: 450 req/s, normal: 200 req/s", value: "94%", threshold: "90%", duration: "15m" },
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
    mutationFn: ({ scenario }: FireAlertPayload) => {
      const payload = SCENARIO_PAYLOADS[scenario];
      return api.post<WebhookResponse>("/alerts/webhook", payload);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["incidents"] });
    },
  });
}
