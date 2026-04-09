import { useIsFetching, useIsMutating } from "@tanstack/react-query";
import { clsx } from "clsx";

export function LiveIndicator() {
  const fetching = useIsFetching();
  const mutating = useIsMutating();
  const active = fetching > 0 || mutating > 0;

  return (
    <span className="flex items-center gap-1.5 text-xs text-zinc-500">
      <span className="relative flex h-2 w-2">
        <span
          className={clsx(
            "absolute inline-flex h-full w-full rounded-full opacity-75",
            active ? "animate-ping bg-emerald-400" : "bg-zinc-600",
          )}
        />
        <span
          className={clsx(
            "relative inline-flex h-2 w-2 rounded-full",
            active ? "bg-emerald-500" : "bg-zinc-600",
          )}
        />
      </span>
      <span className={active ? "text-emerald-400" : "text-zinc-600"}>
        {active ? "live" : "idle"}
      </span>
    </span>
  );
}
