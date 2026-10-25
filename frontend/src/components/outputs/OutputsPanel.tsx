import { useEffect, useState } from "react";
import { api, outputUrl } from "../../api/client";
import { useRoom } from "../../state/RoomContext";
import { ErrorState, LoadingState, Panel } from "../layout/Panel";
import { PvrFormPreview } from "./PvrFormPreview";

interface TaskRecord {
  task_id: string;
  title: string | null;
  description: string;
  owner: string | null;
  reason: string;
  proposed_by: string;
}

interface NotificationRecord {
  notification_id: string;
  recipients: string[];
  message: string;
  proposed_by: string;
}

function useJsonOutput<T>(runId: string | null, file: string, present: boolean): { data: T | null; error: string | null } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!runId || !present) return;
    api
      .outputText(runId, file)
      .then((text) => setData(JSON.parse(text) as T))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : `Could not load ${file}`));
  }, [runId, file, present]);
  return { data, error };
}

/** Stage 7: what the approved actions produced. */
export function OutputsPanel() {
  const { state } = useRoom();
  const files = new Set(state.executed.flatMap((e) => e.files));
  const runId = state.runId;
  const tasks = useJsonOutput<TaskRecord[]>(runId, "tasks.json", files.has("tasks.json"));
  const notes = useJsonOutput<NotificationRecord[]>(runId, "notifications.json", files.has("notifications.json"));

  if (!runId) return null;
  if (state.executed.length === 0) {
    return (
      <Panel title="Outputs">
        <LoadingState
          message={
            state.status === "completed" ? "No actions were approved." : "Nothing is executed until a person approves."
          }
        />
      </Panel>
    );
  }

  return (
    <Panel title="Outputs" right={<span className="text-xs text-text-muted">Written after approval</span>}>
      <div className="grid grid-cols-2 gap-4">
        {files.has("pvr_output_form.html") ? (
          <PvrFormPreview runId={runId} file="pvr_output_form.html" title="PVR output form" />
        ) : null}
        {files.has("verification_report.html") ? (
          <PvrFormPreview runId={runId} file="verification_report.html" title="Verification report" />
        ) : null}

        {files.has("tasks.json") ? (
          <section>
            <h3 className="mb-2 text-sm">Tasks</h3>
            {tasks.error ? <ErrorState message={tasks.error} /> : null}
            <ul className="flex flex-col gap-2 text-sm">
              {(tasks.data ?? []).map((t) => (
                <li key={t.task_id} className="rounded-card border border-border p-3">
                  <div className="font-semibold">
                    {t.task_id} {t.title}
                  </div>
                  {t.owner ? <div className="text-xs text-text-muted">Owner: {t.owner}</div> : null}
                  <div className="text-xs">{t.description || t.reason}</div>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {files.has("notifications.json") ? (
          <section>
            <h3 className="mb-2 text-sm">Notifications</h3>
            {notes.error ? <ErrorState message={notes.error} /> : null}
            <ul className="flex flex-col gap-2 text-sm">
              {(notes.data ?? []).map((n) => (
                <li key={n.notification_id} className="rounded-card border border-border p-3">
                  <div className="text-xs font-semibold text-accent">To {n.recipients.join(", ")}</div>
                  <div className="text-xs">{n.message}</div>
                </li>
              ))}
            </ul>
          </section>
        ) : null}
      </div>
      <div className="mt-3 flex flex-wrap gap-3 text-xs">
        {[...files].map((f) => (
          <a key={f} href={outputUrl(runId, f)} target="_blank" rel="noreferrer" className="text-accent underline">
            {f}
          </a>
        ))}
      </div>
    </Panel>
  );
}
