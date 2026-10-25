import { useEffect, useState } from "react";
import { api, type ChangeType, type StartRunBody } from "../../api/client";
import type { Mode } from "../../api/events";
import { formatParameter } from "../../format";
import { useRoom } from "../../state/RoomContext";
import { ErrorState } from "../layout/Panel";

interface WhatIfControlsProps {
  liveAvailable: boolean | null;
  onRerun: (request: StartRunBody) => Promise<void>;
}

function atDefault(ct: ChangeType, values: Record<string, number>): boolean {
  return ct.parameters.every((p) => Math.abs((values[p.name] ?? p.default) - p.default) < 1e-9);
}

/** What-if: change the size of the change, the contingency or the time buffer, and re-run the agents. */
export function WhatIfControls({ liveAvailable, onRerun }: WhatIfControlsProps) {
  const { state, project } = useRoom();
  const context = state.context;
  const [open, setOpen] = useState(false);
  const [changeType, setChangeType] = useState<ChangeType | null>(null);
  const [values, setValues] = useState<Record<string, number>>({});
  const [contingency, setContingency] = useState("");
  const [buffer, setBuffer] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Start from the current run's change and limits each time the controls open.
  useEffect(() => {
    if (!open || !context) return;
    setValues({ ...context.parameters });
    setContingency(String(context.overrides.cost_contingency_remaining_aed ?? project?.cost_contingency_remaining_aed ?? ""));
    setBuffer(String(context.overrides.time_buffer_working_days ?? project?.time_buffer_working_days ?? ""));
    setError(null);
    api
      .changeTypes()
      .then((all) => setChangeType(all.find((t) => t.id === context.change_type) ?? null))
      .catch(() => setError("Could not load the change type"));
  }, [open, context, project]);

  if (!context) return null;

  const rerun = async () => {
    if (!changeType) return;
    const contractor: Mode = "contractor_pvr";
    const mode: Mode = context.mode === contractor && atDefault(changeType, values) ? contractor : "internal_what_if";
    const asNumber = (text: string) => (text.trim() === "" ? null : Number(text));
    const overrides = {
      cost_contingency_remaining_aed: asNumber(contingency),
      time_buffer_working_days: asNumber(buffer),
    };
    if (Object.values(overrides).some((v) => v !== null && !Number.isFinite(v))) {
      setError("Contingency and time buffer must be numbers.");
      return;
    }
    // Keep the project's values as "no override", so the run shows them as the defaults they are.
    if (overrides.cost_contingency_remaining_aed === project?.cost_contingency_remaining_aed) {
      overrides.cost_contingency_remaining_aed = null;
    }
    if (overrides.time_buffer_working_days === project?.time_buffer_working_days) overrides.time_buffer_working_days = null;
    setBusy(true);
    setError(null);
    try {
      await onRerun({ change_type: context.change_type, parameters: values, mode, overrides });
      setOpen(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "The run could not start");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="shrink-0 rounded-card border border-border bg-bg" aria-label="What-if">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full items-center justify-between px-4 py-2.5 text-left"
      >
        <span className="text-sm font-semibold text-accent">What-if</span>
        <span className="text-xs text-text-muted">
          {open ? "Hide" : "Change the size, the contingency or the time buffer, and re-run the agents"}
        </span>
      </button>
      {open ? (
        <div className="flex flex-wrap items-end gap-6 border-t border-border px-4 py-3 text-sm">
          {changeType?.parameters.map((p) => (
            <label key={p.name} className="flex w-56 flex-col gap-1">
              <span className="flex justify-between">
                <span className="font-semibold">{p.label}</span>
                <span className="font-bold text-accent">{formatParameter(values[p.name] ?? p.default, p.step)}</span>
              </span>
              <input
                type="range"
                min={p.min}
                max={p.max}
                step={p.step}
                value={values[p.name] ?? p.default}
                onChange={(e) => setValues((old) => ({ ...old, [p.name]: Number(e.target.value) }))}
                className="accent-[var(--accent)]"
                aria-label={p.label}
              />
            </label>
          ))}
          <label className="flex flex-col gap-1">
            <span className="font-semibold">Cost contingency (AED)</span>
            <input
              type="number"
              step={1000}
              value={contingency}
              onChange={(e) => setContingency(e.target.value)}
              className="w-36 rounded border border-border px-2 py-1"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="font-semibold">Time buffer (working days)</span>
            <input
              type="number"
              min={0}
              step={1}
              value={buffer}
              onChange={(e) => setBuffer(e.target.value)}
              className="w-36 rounded border border-border px-2 py-1"
            />
          </label>
          <div className="flex flex-col gap-1">
            <button
              type="button"
              onClick={() => void rerun()}
              disabled={busy || !changeType || liveAvailable === false}
              className="rounded-full bg-accent px-5 py-2 font-semibold text-white disabled:opacity-40"
            >
              {busy ? "Starting…" : "Re-run agents"}
            </button>
            <span className="text-[11px] text-text-muted">
              {liveAvailable === false ? "Needs an OpenAI API key." : "Starts a new live run with the language model."}
            </span>
          </div>
          {error ? (
            <div className="w-full">
              <ErrorState message={error} />
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
