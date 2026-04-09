import { clsx } from "clsx";

export function Spinner({ className }: { className?: string }) {
  return (
    <svg
      className={clsx("animate-spin", className ?? "h-4 w-4 text-zinc-400")}
      fill="none"
      viewBox="0 0 24 24"
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
      />
    </svg>
  );
}
