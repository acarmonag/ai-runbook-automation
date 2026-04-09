import { useState } from "react";
import { useRunbooks } from "@/hooks/useRunbooks";
import { RunbookCard } from "@/components/runbooks/RunbookCard";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { Search } from "lucide-react";

export function RunbooksPage() {
  const { data: runbooks, isLoading } = useRunbooks();
  const [query, setQuery] = useState("");

  const filtered = (runbooks ?? []).filter(
    (r) =>
      r.name.toLowerCase().includes(query.toLowerCase()) ||
      r.triggers.some((t) => t.toLowerCase().includes(query.toLowerCase())),
  );

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-zinc-300">
          Runbooks {runbooks ? `(${runbooks.length})` : ""}
        </h2>
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-zinc-500" />
          <input
            type="text"
            placeholder="Search..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="rounded border border-zinc-700 bg-surface-1 py-1.5 pl-8 pr-3 text-xs text-zinc-300 placeholder:text-zinc-600 focus:border-zinc-500 focus:outline-none w-48"
          />
        </div>
      </div>

      {isLoading && !runbooks ? (
        <div className="flex justify-center py-10">
          <Spinner className="h-6 w-6 text-zinc-500" />
        </div>
      ) : filtered.length === 0 ? (
        <EmptyState title="No runbooks found" description={query ? "Try a different search term." : undefined} />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((rb) => (
            <RunbookCard key={rb.name} runbook={rb} />
          ))}
        </div>
      )}
    </div>
  );
}
