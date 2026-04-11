import { useState } from "react";
import type { Runbook } from "@/types/runbook";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { useRunbookYaml } from "@/hooks/useRunbookYaml";
import { useUpdateRunbook } from "@/hooks/useUpdateRunbook";
import { useQueryClient } from "@tanstack/react-query";

export function RunbookCard({ runbook }: { runbook: Runbook }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedOk, setSavedOk] = useState(false);
  const queryClient = useQueryClient();

  const { data: yamlContent, isLoading: yamlLoading } = useRunbookYaml(
    runbook.name,
    editing,
  );

  const { mutate: saveRunbook, isPending: saving } = useUpdateRunbook(runbook.name);

  function openEditor() {
    setSaveError(null);
    setSavedOk(false);
    setEditing(true);
  }

  function closeEditor() {
    setEditing(false);
    setDraft(null);
    setSaveError(null);
  }

  function handleSave() {
    const yaml = draft ?? yamlContent ?? "";
    setSaveError(null);
    saveRunbook(yaml, {
      onSuccess: () => {
        setSavedOk(true);
        // Invalidate cached YAML so next open fetches fresh
        queryClient.invalidateQueries({ queryKey: ["runbook-yaml", runbook.name] });
        setTimeout(() => {
          setSavedOk(false);
          closeEditor();
        }, 1200);
      },
      onError: (err) => setSaveError(err.message),
    });
  }

  return (
    <Card>
      <div className="mb-2 flex items-start justify-between gap-2">
        <h3 className="font-mono text-sm font-semibold text-zinc-100">{runbook.name}</h3>
        <div className="flex flex-wrap gap-1">
          {runbook.metadata?.severity && (
            <Badge className="bg-zinc-800 text-zinc-400 text-xs">
              {runbook.metadata.severity}
            </Badge>
          )}
          {runbook.metadata?.team && (
            <Badge className="bg-zinc-800 text-zinc-400 text-xs">
              {runbook.metadata.team}
            </Badge>
          )}
        </div>
      </div>

      <p className="mb-3 text-xs text-zinc-500 leading-relaxed">{runbook.description}</p>

      <div className="mb-3">
        <p className="mb-1 text-xs font-medium text-zinc-400">Triggers</p>
        <div className="flex flex-wrap gap-1">
          {runbook.triggers.map((t) => (
            <Badge key={t} className="bg-amber-900/40 text-amber-300 border border-amber-800/50">
              {t}
            </Badge>
          ))}
        </div>
      </div>

      {runbook.actions && runbook.actions.length > 0 && (
        <div className="mb-3">
          <p className="mb-1 text-xs font-medium text-zinc-400">
            Actions ({runbook.actions.length})
          </p>
          <ol className="flex flex-col gap-1">
            {runbook.actions.map((a, i) => (
              <li key={i} className="flex gap-2 text-xs text-zinc-500">
                <span className="shrink-0 text-zinc-600">{i + 1}.</span>
                <span>{a}</span>
              </li>
            ))}
          </ol>
        </div>
      )}

      {runbook.escalation_threshold && (
        <div className="mt-2 rounded bg-zinc-800/40 px-3 py-2 mb-3">
          <p className="mb-0.5 text-xs font-medium text-zinc-400">Escalation</p>
          <p className="text-xs text-zinc-500">{runbook.escalation_threshold}</p>
        </div>
      )}

      {/* Edit button */}
      {!editing && (
        <button
          onClick={openEditor}
          className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          Edit YAML ›
        </button>
      )}

      {/* Inline YAML editor */}
      {editing && (
        <div className="mt-3 space-y-2">
          {yamlLoading ? (
            <div className="flex justify-center py-4">
              <Spinner className="h-4 w-4 text-zinc-500" />
            </div>
          ) : (
            <textarea
              className="w-full rounded border border-zinc-700 bg-zinc-900 p-2 font-mono text-xs text-zinc-300
                         focus:border-zinc-500 focus:outline-none resize-y"
              rows={20}
              value={draft ?? yamlContent ?? ""}
              onChange={(e) => setDraft(e.target.value)}
              spellCheck={false}
            />
          )}

          {saveError && (
            <p className="text-xs text-red-400">{saveError}</p>
          )}

          {savedOk && (
            <p className="text-xs text-emerald-400">Saved successfully.</p>
          )}

          <div className="flex gap-2">
            <Button
              onClick={handleSave}
              disabled={saving || yamlLoading}
              className="bg-emerald-700 hover:bg-emerald-600 text-white px-3 py-1 text-xs rounded"
            >
              {saving ? "Saving…" : "Save"}
            </Button>
            <button
              onClick={closeEditor}
              className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </Card>
  );
}
