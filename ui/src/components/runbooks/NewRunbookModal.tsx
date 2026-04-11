import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { useCreateRunbook } from "@/hooks/useCreateRunbook";

const TEMPLATE = `name: my_runbook
description: |
  Describe what this runbook handles and when to use it.

triggers:
  - MyAlertName

actions:
  - "get_metrics: Query the relevant metric"
  - "get_recent_logs: Check service logs for error patterns"
  - "run_diagnostic: Run relevant diagnostic check"
  - "restart_service: Restart if logs confirm crash pattern (requires approval)"

escalation_threshold: |
  Escalate if metric remains above threshold after remediation,
  or if root cause is unknown after full investigation.

metadata:
  severity: P2
  team: platform
  runbook_version: "1.0"
`;

interface NewRunbookModalProps {
  onClose: () => void;
}

export function NewRunbookModal({ onClose }: NewRunbookModalProps) {
  const [yaml, setYaml] = useState(TEMPLATE);
  const { mutate: createRunbook, isPending, isError, error } = useCreateRunbook();
  const backdropRef = useRef<HTMLDivElement>(null);

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  function handleSave() {
    createRunbook(yaml, {
      onSuccess: () => onClose(),
    });
  }

  function handleBackdropClick(e: React.MouseEvent) {
    if (e.target === backdropRef.current) onClose();
  }

  return (
    <div
      ref={backdropRef}
      onClick={handleBackdropClick}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
    >
      <div className="w-full max-w-2xl rounded-xl border border-zinc-700 bg-zinc-900 shadow-2xl flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800">
          <h2 className="text-sm font-semibold text-zinc-100">New Runbook</h2>
          <button
            onClick={onClose}
            className="text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Editor */}
        <div className="flex-1 overflow-hidden px-5 py-4">
          <p className="mb-2 text-xs text-zinc-500">
            Edit the YAML template below. The <code className="text-zinc-400">name</code> field
            determines the runbook filename. Change it before saving.
          </p>
          <textarea
            className="w-full h-80 rounded border border-zinc-700 bg-zinc-950 p-3 font-mono text-xs
                       text-zinc-300 focus:border-zinc-500 focus:outline-none resize-y"
            value={yaml}
            onChange={(e) => setYaml(e.target.value)}
            spellCheck={false}
          />
          {isError && (
            <p className="mt-2 text-xs text-red-400">
              {(error as Error).message}
            </p>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-5 py-4 border-t border-zinc-800">
          <button
            onClick={onClose}
            className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            Cancel
          </button>
          <Button onClick={handleSave} disabled={isPending}>
            {isPending && <Spinner className="h-3.5 w-3.5" />}
            Create Runbook
          </Button>
        </div>
      </div>
    </div>
  );
}
