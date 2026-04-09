import { clsx } from "clsx";

interface BadgeProps {
  children: React.ReactNode;
  className?: string;
}

export function Badge({ children, className }: BadgeProps) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-medium",
        className,
      )}
    >
      {children}
    </span>
  );
}
