import { useEffect, useMemo, useState } from "react";
import { api, type ChangeType, type StartRunBody, type StoredRun } from "../../api/client";
import type { Mode } from "../../api/events";
import { CHANGE_LABEL, fillTemplate, formatDate, formatParameter } from "../../format";
import { EmptyState, ErrorState, LoadingState, Panel } from "../layout/Panel";

const CARD_TEXT: Record<string, string> = {
  wall_height: "Higher wall on a chain with some float: a real trade-off between cost, time and contingency.",
  road_widening: "Wider road on the critical path: every added day delays completion.",
  paving_area: "More paving on a chain with plenty of float: a cost-only decision.",
};

const MODE_LABEL: Record<Mode, string> = {
  contractor_pvr: "Contractor PVR (check the contractor's claim)",
  internal_what_if: "Internal what-if (assess before announcing)",
};

export type RunRequest = StartRunBody;

interface ChangeSelectorProps {
  liveAvailable: boolean | null;
  onRun: (request: RunRequest) => Promise<void>;
  onReplay: (traceId: string) => void;
}

function defaults(ct: ChangeType): Record<string, number> {
  return Object.fromEntries(ct.parameters.map((p) => [p.name, p.default]));
}

function atDefault(ct: ChangeType, values: Record<string, number>): boolean {
  return ct.parameters.every((p) => Math.abs((values[p.name] ?? p.default) - p.default) < 1e-9);
}

/** Start screen: choose a change and its size, then run the agents or replay a saved run. */
export function ChangeSelector({ liveAvailable, onRun, onReplay }: ChangeSelectorProps) {
  const [types, setTypes] = useState<ChangeType[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [values, setValues] = useState<Record<string, number>>({});
  const [mode, setMode] = useState<Mode>("internal_what_if");
  const [starting, setStarting] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  useEffect(() => {
    api
      .changeTypes()
      .then(setTypes)
      .catch((e: unknown) => setLoadError(e instanceof Error ? e.message : "Could not load the change types"));
  }, []);

  const changeType = types?.find((t) => t.id === selected) ?? null;
  const contractorAllowed =
    changeType !== null &&
    changeType.modes.includes("contractor_pvr") &&
    changeType.has_contractor_claim_at_default &&
    atDefault(changeType, values);
  const effectiveMode: Mode = contractorAllowed ? mode : "internal_what_if";

  const choose = (ct: ChangeType) => {
    setSelected(ct.id);
    setValues(defaults(ct));
    setMode(ct.modes[0] ?? "internal_what_if");
    setRunError(null);
  };

  const instruction = useMemo(() => {
    if (!changeType) return "";
    const steps = Object.fromEntries(changeType.parameters.map((p) => [p.name, p.step]));
    return fillTemplate(changeType.default_instruction, values, steps);
  }, [changeType, values]);

  const run = async () => {
    if (!changeType) return;
    setStarting(true);
    setRunError(null);
    try {
      await onRun({ change_type: changeType.id, parameters: values, mode: effectiveMode });
    } catch (e) {
      setRunError(e instanceof Error ? e.message : "The run could not start");
      setStarting(false);
    }
  };

  return (
    <main className="grid min-h-0 flex-1 grid-cols-[3fr_2fr] gap-4 bg-surface p-4">
      <div className="flex min-h-0 flex-col gap-4 overflow-y-auto">
        <Panel title="Choose a change, and set its size" className="shrink-0">
          {loadError ? <ErrorState message={`Could not reach the backend: ${loadError}`} /> : null}
          {!types && !loadError ? <LoadingState message="Loading the change types" /> : null}
          {types ? (
            <div className="grid grid-cols-3 gap-3">
              {types.map((ct) => (
                <button
                  key={ct.id}
                  type="button"
                  onClick={() => choose(ct)}
                  aria-pressed={selected === ct.id}
                  className={`flex flex-col gap-2 rounded-card border p-4 text-left transition-colors ${
                    selected === ct.id ? "border-accent bg-accent-tint" : "border-border bg-bg hover:border-accent-2"
                  }`}
                >
                  <span className="font-semibold text-accent">{CHANGE_LABEL[ct.id] ?? ct.title}</span>
                  <span className="text-xs leading-relaxed text-text-muted">{CARD_TEXT[ct.id] ?? ""}</span>
                </button>
              ))}
            </div>
          ) : null}

          {changeType ? (
            <div className="mt-5 flex flex-col gap-5">
              {changeType.parameters.map((p) => {
                const value = values[p.name] ?? p.default;
                return (
                  <label key={p.name} className="flex flex-col gap-2 text-sm">
                    <span className="flex items-center justify-between">
                      <span className="font-semibold">{p.label}</span>
                      <input
                        type="number"
                        min={p.min}
                        max={p.max}
                        step={p.step}
                        value={value}
                        onChange={(e) => {
                          const v = Number(e.target.value);
                          if (Number.isFinite(v)) setValues((old) => ({ ...old, [p.name]: v }));
                        }}
                        className="w-24 rounded border border-border px-2 py-1 text-right font-bold text-accent"
                        aria-label={`${p.label} value`}
                      />
                    </span>
                    <input
                      type="range"
                      min={p.min}
                      max={p.max}
                      step={p.step}
                      value={value}
                      onChange={(e) => setValues((old) => ({ ...old, [p.name]: Number(e.target.value) }))}
                      className="accent-[var(--accent)]"
                      aria-label={p.label}
                    />
                    <span className="flex justify-between text-xs text-text-muted">
                      <span>{formatParameter(p.min, p.step)}</span>
                      <span>default {formatParameter(p.default, p.step)}</span>
                      <span>{formatParameter(p.max, p.step)}</span>
                    </span>
                  </label>
                );
              })}

              {changeType.modes.includes("contractor_pvr") ? (
                <fieldset className="flex flex-col gap-2 text-sm">
                  <legend className="mb-1 font-semibold">Mode</legend>
                  {changeType.modes.map((m) => {
                    const disabled = m === "contractor_pvr" && !contractorAllowed;
                    return (
                      <label key={m} className={`flex items-center gap-2 ${disabled ? "text-text-muted" : ""}`}>
                        <input
                          type="radio"
                          name="mode"
                          value={m}
                          checked={effectiveMode === m}
                          disabled={disabled}
                          onChange={() => setMode(m)}
                        />
                        {MODE_LABEL[m]}
                        {disabled ? <span className="text-xs">(only at the default size)</span> : null}
                      </label>
                    );
                  })}
                </fieldset>
              ) : null}

              <div className="rounded-card bg-surface p-4">
                <div className="mb-1 text-xs font-semibold text-text-muted">Instruction</div>
                <p className="text-sm leading-relaxed">{instruction}</p>
              </div>

              {runError ? <ErrorState message={runError} /> : null}
              {liveAvailable === false ? (
                <ErrorState message="Live runs need an OpenAI API key in .env. Saved runs can still be replayed." />
              ) : null}
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => void run()}
                  disabled={starting || liveAvailable === false}
                  className="rounded-full bg-accent px-6 py-2.5 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-40"
                >
                  {starting ? "Starting…" : "Run agents"}
                </button>
                <span className="text-xs text-text-muted">
                  Seven agents assess, debate and prepare a decision. Nothing is executed until you approve.
                </span>
              </div>
            </div>
          ) : null}
        </Panel>

        <SavedRuns onReplay={onReplay} />
      </div>

      <ProjectData />
    </main>
  );
}

function SavedRuns({ onReplay }: { onReplay: (traceId: string) => void }) {
  const [runs, setRuns] = useState<StoredRun[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listRuns()
      .then((all) => setRuns(all.filter((r) => r.kind === "full" && ["completed", "rejected"].includes(r.state))))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Could not load saved runs"));
  }, []);

  return (
    <Panel title="Replay a saved run" className="shrink-0">
      {error ? <ErrorState message={error} /> : null}
      {!runs && !error ? <LoadingState message="Loading saved runs" /> : null}
      {runs && runs.length === 0 ? <EmptyState message="No saved runs yet." /> : null}
      {runs && runs.length > 0 ? (
        <ul className="flex flex-col divide-y divide-border">
          {runs.map((r) => (
            <li key={r.id} className="flex items-center justify-between gap-3 py-2 text-sm">
              <div className="min-w-0">
                <div className="font-semibold">
                  {r.change_type ? CHANGE_LABEL[r.change_type] ?? r.change_type : r.id}
                  {r.source === "fixture" ? (
                    <span className="ml-2 rounded-full bg-accent-tint px-2 py-0.5 text-[10px] text-accent">demo</span>
                  ) : null}
                </div>
                <div className="truncate text-xs text-text-muted">
                  {r.parameters
                    ? Object.entries(r.parameters)
                        .map(([k, v]) => `${k.replace(/_/g, " ")} ${v}`)
                        .join(", ")
                    : ""}
                  {r.mode === "contractor_pvr" ? " · contractor PVR" : ""}
                  {r.started_at ? ` · ${formatDate(r.started_at)}` : ""}
                  {r.chosen_option ? ` · approved ${r.chosen_option}` : r.state === "rejected" ? " · rejected" : ""}
                </div>
              </div>
              <button
                type="button"
                onClick={() => onReplay(r.id)}
                className="shrink-0 rounded-full border border-accent px-4 py-1 text-xs font-semibold text-accent hover:bg-accent hover:text-white"
              >
                Replay
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </Panel>
  );
}

interface BoqRow {
  code: string;
  bill_name: string;
  description: string;
  unit: string;
  quantity: number;
  rate_aed: number;
}

/** The given project data, for reference before a run (SPEC 17 step 1). */
function ProjectData() {
  const [tab, setTab] = useState<"Contract" | "BOQ">("Contract");
  const [boq, setBoq] = useState<BoqRow[] | null>(null);
  const [clauses, setClauses] = useState<{ clause: string; title: string; text: string }[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([fetch("/api/data/boq").then((r) => r.json() as Promise<BoqRow[]>), api.contract()])
      .then(([b, c]) => {
        setBoq(b);
        setClauses(c.clauses);
      })
      .catch(() => setError("Could not load the project data"));
  }, []);

  return (
    <Panel
      title="Project data"
      right={
        <div className="flex gap-1" role="tablist" aria-label="Project data">
          {(["Contract", "BOQ"] as const).map((t) => (
            <button
              key={t}
              type="button"
              role="tab"
              aria-selected={tab === t}
              onClick={() => setTab(t)}
              className={`rounded-full px-3 py-1 text-xs ${tab === t ? "bg-accent text-white" : "text-text-muted"}`}
            >
              {t === "BOQ" ? "BOQ (bill of quantities)" : "Contract clauses"}
            </button>
          ))}
        </div>
      }
    >
      {error ? <ErrorState message={error} /> : null}
      {!error && (!boq || !clauses) ? <LoadingState message="Loading project data" /> : null}
      {tab === "Contract" && clauses ? (
        <ul className="flex flex-col gap-3">
          {clauses.map((c) => (
            <li key={c.clause} className="text-sm">
              <div className="font-semibold text-accent">
                {c.clause} {c.title}
              </div>
              <p className="text-xs leading-relaxed text-text-muted">{c.text}</p>
            </li>
          ))}
        </ul>
      ) : null}
      {tab === "BOQ" && boq ? (
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-bg text-left text-text-muted">
            <tr>
              <th className="py-1 pr-2">Code</th>
              <th className="py-1 pr-2">Description</th>
              <th className="py-1 pr-2 text-right">Quantity</th>
              <th className="py-1 text-right">Rate (AED)</th>
            </tr>
          </thead>
          <tbody>
            {boq.map((row) => (
              <tr key={row.code} className="border-t border-border align-top">
                <td className="py-1 pr-2 font-mono whitespace-nowrap">{row.code}</td>
                <td className="py-1 pr-2">{row.description}</td>
                <td className="py-1 pr-2 text-right whitespace-nowrap">
                  {row.quantity.toLocaleString("en-GB")} {row.unit}
                </td>
                <td className="py-1 text-right">{row.rate_aed.toLocaleString("en-GB")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </Panel>
  );
}
