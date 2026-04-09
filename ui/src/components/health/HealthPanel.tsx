import { useHealth } from "@/hooks/useHealth";
import { Card } from "@/components/ui/Card";
import { clsx } from "clsx";
import { Spinner } from "@/components/ui/Spinner";

function MetricRow({
  label,
  value,
  ok,
}: {
  label: string;
  value: string | number;
  ok?: boolean;
}) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-zinc-800/50 last:border-0">
      <span className="text-xs text-zinc-500">{label}</span>
      <span
        className={clsx(
          "text-xs font-medium",
          ok === true
            ? "text-emerald-400"
            : ok === false
              ? "text-red-400"
              : "text-zinc-300",
        )}
      >
        {String(value)}
      </span>
    </div>
  );
}

export function HealthPanel() {
  const { data, isLoading } = useHealth();

  return (
    <Card title="Service Health">
      {isLoading && !data ? (
        <div className="flex justify-center py-4">
          <Spinner />
        </div>
      ) : !data ? (
        <p className="text-xs text-zinc-500">Unavailable</p>
      ) : (
        <div>
          <MetricRow
            label="Overall"
            value={data.status}
            ok={data.status === "healthy"}
          />
          <MetricRow
            label="LLM"
            value={data.claude_api}
            ok={data.claude_api === "reachable"}
          />
          <MetricRow
            label="Prometheus"
            value={data.prometheus}
            ok={data.prometheus === "reachable"}
          />
          <MetricRow label="Queue depth" value={data.queue_depth} />
          <MetricRow label="Active workers" value={data.active_workers} />
          <MetricRow label="Processed" value={data.incidents_processed} />
        </div>
      )}
    </Card>
  );
}
