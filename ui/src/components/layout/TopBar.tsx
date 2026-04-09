import { LiveIndicator } from "./LiveIndicator";
import { useHealth } from "@/hooks/useHealth";
import { clsx } from "clsx";

export function TopBar() {
  const { data: health } = useHealth();

  const statusColor =
    health?.status === "healthy"
      ? "text-emerald-400"
      : health?.status === "degraded"
        ? "text-amber-400"
        : "text-red-400";

  return (
    <header className="flex h-11 items-center justify-between border-b border-zinc-800 bg-surface-1 px-4">
      <span className="text-xs text-zinc-500">AI Runbook Automation</span>

      <div className="flex items-center gap-4">
        {health && (
          <span className={clsx("text-xs font-medium", statusColor)}>
            {health.status.toUpperCase()}
          </span>
        )}
        <LiveIndicator />
      </div>
    </header>
  );
}
