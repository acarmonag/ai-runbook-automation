import { clsx } from "clsx";

interface CardProps {
  children: React.ReactNode;
  className?: string;
  title?: string;
}

export function Card({ children, className, title }: CardProps) {
  return (
    <div className={clsx("rounded-lg border border-zinc-800 bg-surface-1", className)}>
      {title && (
        <div className="border-b border-zinc-800 px-4 py-2.5">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-400">{title}</h3>
        </div>
      )}
      <div className="p-4">{children}</div>
    </div>
  );
}
