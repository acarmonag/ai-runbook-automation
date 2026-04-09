import { clsx } from "clsx";

const config: Record<string, string> = {
  critical: "bg-red-900/50 text-red-300 border border-red-700",
  warning:  "bg-amber-900/50 text-amber-300 border border-amber-700",
  info:     "bg-blue-900/50 text-blue-300 border border-blue-700",
};

export function SeverityBadge({ severity }: { severity?: string }) {
  if (!severity) return null;
  return (
    <span className={clsx("inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium capitalize", config[severity] ?? config.info)}>
      {severity}
    </span>
  );
}
