import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";

export type ModalKind = "approve" | "reject";

interface ApprovalModalProps {
  kind: ModalKind | null;
  summary: string[];
  busy: boolean;
  error: string | null;
  onConfirm: (reason: string) => void;
  onCancel: () => void;
}

/** Confirmation before a decision takes effect (a page dialog, never a browser alert). */
export function ApprovalModal({ kind, summary, busy, error, onConfirm, onCancel }: ApprovalModalProps) {
  const [reason, setReason] = useState("");
  return (
    <AnimatePresence>
      {kind ? (
        <motion.div
          key="backdrop"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/30"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label={kind === "approve" ? "Confirm approval" : "Confirm rejection"}
            className="w-[460px] rounded-card bg-bg p-6 shadow-2xl"
            initial={{ scale: 0.95, y: 10 }}
            animate={{ scale: 1, y: 0 }}
          >
            <h2 className="mb-3 text-lg">{kind === "approve" ? "Approve this decision?" : "Reject this assessment?"}</h2>
            <ul className="mb-4 flex flex-col gap-1 text-sm">
              {summary.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
            {kind === "reject" ? (
              <label className="mb-4 flex flex-col gap-1 text-sm">
                <span className="font-semibold">Reason</span>
                <textarea
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  rows={3}
                  className="rounded border border-border p-2"
                />
              </label>
            ) : (
              <p className="mb-4 text-xs text-text-muted">
                The approved actions are executed straight away and their files written to the run folder.
              </p>
            )}
            {error ? <p className="mb-3 text-sm text-alert">{error}</p> : null}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={onCancel} disabled={busy} className="rounded-full px-4 py-2 text-sm text-text-muted">
                Cancel
              </button>
              <button
                type="button"
                onClick={() => onConfirm(reason)}
                disabled={busy || (kind === "reject" && !reason.trim())}
                className="rounded-full bg-accent px-5 py-2 text-sm font-semibold text-white disabled:opacity-40"
              >
                {busy ? "Working…" : kind === "approve" ? "Approve" : "Reject"}
              </button>
            </div>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
