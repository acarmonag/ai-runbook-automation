import { useState } from "react";
import { useFireAlert, type Scenario } from "@/hooks/useFireAlert";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { Zap } from "lucide-react";
import { Card } from "@/components/ui/Card";

const SCENARIOS: { value: Scenario; label: string; severity: string; action: string }[] = [
  { value: "high_error_rate",           label: "High Error Rate",         severity: "critical", action: "restart"  },
  { value: "high_latency",              label: "High Latency",            severity: "warning",  action: "restart"  },
  { value: "memory_leak",               label: "Memory Leak",             severity: "warning",  action: "restart"  },
  { value: "service_down",              label: "Service Down",            severity: "critical", action: "restart"  },
  { value: "cpu_spike",                 label: "CPU Spike",               severity: "warning",  action: "restart"  },
  { value: "database_connection_pool",  label: "DB Connection Pool",      severity: "critical", action: "restart"  },
  { value: "network_latency",           label: "Network Latency",         severity: "warning",  action: "escalate" },
  { value: "circuit_breaker_open",      label: "Circuit Breaker Open",    severity: "critical", action: "escalate" },
  { value: "disk_pressure",             label: "Disk Pressure",           severity: "warning",  action: "escalate" },
  { value: "service_degradation_scale", label: "Service Degradation",     severity: "warning",  action: "scale"    },
  { value: "dependency_failure",        label: "Dependency Failure",      severity: "critical", action: "escalate" },
  { value: "high_traffic_load",         label: "High Traffic (Scale)",    severity: "warning",  action: "scale"    },
  { value: "cache_exhaustion",          label: "Cache Exhaustion",        severity: "warning",  action: "scale"    },
  { value: "downstream_dependency",     label: "Downstream Dependency",   severity: "critical", action: "escalate" },
  { value: "pod_crashloop",             label: "Pod CrashLoop",           severity: "critical", action: "scale"    },
];

const severityColor: Record<string, string> = {
  critical: "text-red-400",
  warning:  "text-amber-400",
};

const actionHint: Record<string, string> = {
  restart:  "Expected action: restart service",
  scale:    "Expected action: scale service",
  escalate: "Expected action: escalate to on-call",
};

export function AlertSimulator() {
  const [scenario, setScenario] = useState<Scenario>("high_error_rate");
  const { mutate: fireAlert, isPending, isSuccess, isError, error, data } = useFireAlert();

  const handleFire = () => fireAlert({ scenario });

  return (
    <Card title="Alert Simulator">
      <div className="flex flex-col gap-3">
        <div>
          <label className="mb-1 block text-xs text-zinc-500">Scenario</label>
          <select
            value={scenario}
            onChange={(e) => setScenario(e.target.value as Scenario)}
            className="w-full rounded border border-zinc-700 bg-surface-2 px-3 py-1.5 text-sm text-zinc-200 focus:border-zinc-500 focus:outline-none"
          >
            {SCENARIOS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
          {(() => {
            const s = SCENARIOS.find(sc => sc.value === scenario);
            return s ? (
              <div className="mt-1 flex items-center gap-2">
                <span className={`text-xs ${severityColor[s.severity]}`}>{s.severity}</span>
                <span className="text-xs text-zinc-600">·</span>
                <span className="text-xs text-zinc-500">{actionHint[s.action]}</span>
              </div>
            ) : null;
          })()}
        </div>

        <Button onClick={handleFire} disabled={isPending} className="w-full justify-center">
          {isPending ? <Spinner className="h-3.5 w-3.5" /> : <Zap className="h-3.5 w-3.5" />}
          Fire Alert
        </Button>

        {isSuccess && data && (
          <div className="rounded border border-emerald-800 bg-emerald-950/30 px-3 py-2 text-xs text-emerald-300">
            Queued {data.incidents_queued} alert — ID: {data.incident_ids[0]}
          </div>
        )}

        {isError && (
          <div className="rounded border border-red-800 bg-red-950/30 px-3 py-2 text-xs text-red-300">
            {(error as Error).message}
          </div>
        )}
      </div>
    </Card>
  );
}
