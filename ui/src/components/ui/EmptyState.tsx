import { Inbox } from "lucide-react";

interface EmptyStateProps {
  title: string;
  description?: string;
}

export function EmptyState({ title, description }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-16 text-zinc-500">
      <Inbox className="h-10 w-10 opacity-40" />
      <p className="text-sm font-medium text-zinc-400">{title}</p>
      {description && <p className="text-xs">{description}</p>}
    </div>
  );
}
