import { useState } from "react";
import { Plus, Search } from "lucide-react";
import { useRunbooks } from "@/hooks/useRunbooks";
import { RunbookCard } from "@/components/runbooks/RunbookCard";
import { NewRunbookModal } from "@/components/runbooks/NewRunbookModal";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";

export function RunbooksPage() {
  const { data: runbooks, isLoading } = useRunbooks();
  const [query, setQuery] = useState("");
  const [showModal, setShowModal] = useState(false);

  const filtered = (runbooks ?? []).filter(
    (r) =>
      r.name.toLowerCase().includes(query.toLowerCase()) ||
      r.triggers.some((t) => t.toLowerCase().includes(query.toLowerCase())),
  );

  return (
    <div>
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-zinc-300">
          Runbooks {runbooks ? `(${runbooks.length})` : ""}
        </h2>

        <div className="flex items-center gap-2 ml-auto">
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
          <Button onClick={() => setShowModal(true)}>
            <Plus className="h-3.5 w-3.5" />
            New Runbook
          </Button>
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

      {showModal && <NewRunbookModal onClose={() => setShowModal(false)} />}
    </div>
  );
}
