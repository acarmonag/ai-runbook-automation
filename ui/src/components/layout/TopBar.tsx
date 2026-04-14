import { clsx } from "clsx";
import { Bot, Hand, Loader2 } from "lucide-react";
import { LiveIndicator } from "./LiveIndicator";
import { useHealth } from "@/hooks/useHealth";
import { useAgentMode } from "@/hooks/useAgentMode";

function AgentModeToggle() {
  const { mode, isSwitching, setMode } = useAgentMode();

  const isAuto = mode === "AUTO";
  const isDry  = mode === "DRY_RUN";

  function toggle() {
    // Cycle: AUTO → MANUAL → AUTO (DRY_RUN stays until explicitly set via API)
    if (isDry) return; // don't let the UI override DRY_RUN
    setMode(isAuto ? "MANUAL" : "AUTO");
  }

  return (
    <button
      type="button"
      onClick={toggle}
      disabled={isSwitching || isDry}
      title={
        isDry
          ? "DRY_RUN mode — set via environment variable"
          : isAuto
            ? "Agent is autonomous — click to require human approval"
            : "Agent waits for approval — click to make autonomous"
      }
      className={clsx(
        "flex items-center gap-1.5 rounded border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide transition-colors",
        isSwitching && "opacity-50 cursor-not-allowed",
        !isSwitching && !isDry && "cursor-pointer",
        isDry  && "border-zinc-600/50 bg-zinc-800/40 text-zinc-500 cursor-default",
        !isDry && isAuto  && "border-emerald-700/60 bg-emerald-950/40 text-emerald-400 hover:bg-emerald-900/40",
        !isDry && !isAuto && "border-amber-700/60  bg-amber-950/40  text-amber-400  hover:bg-amber-900/40",
      )}
    >
      {isSwitching ? (
        <Loader2 className="h-3 w-3 animate-spin" />
      ) : isAuto ? (
        <Bot className="h-3 w-3" />
      ) : (
        <Hand className="h-3 w-3" />
      )}
      <span>
        {isDry ? "DRY RUN" : isAuto ? "AUTO" : "MANUAL"}
      </span>
    </button>
  );
}

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

      <div className="flex items-center gap-3">
        {health && (
          <span className={clsx("text-xs font-medium", statusColor)}>
            {health.status.toUpperCase()}
          </span>
        )}
        <AgentModeToggle />
        <LiveIndicator />
      </div>
    </header>
  );
}
