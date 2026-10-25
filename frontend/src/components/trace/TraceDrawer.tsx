import { AnimatePresence, motion } from "framer-motion";
import { useMemo, useState } from "react";
import type { RunEvent } from "../../api/events";
import { formatNumber } from "../../format";
import { agentLabel } from "../../state/agents";
import { useRoom } from "../../state/RoomContext";

/** Event groups for filtering. */
const GROUPS: { id: string; label: string; types: RunEvent["type"][] }[] = [
  { id: "stages", label: "Stages", types: ["run.started", "stage.started", "stage.completed", "run.completed"] },
  { id: "agents", label: "Agent turns", types: ["agent.active", "agent.idle"] },
  { id: "llm", label: "Model calls", types: ["llm.call"] },
  { id: "tools", label: "Tool calls", types: ["tool.called", "tool.result"] },
  { id: "facts", label: "Facts", types: ["fact.registered"] },
  {
    id: "messages",
    label: "Messages",
    types: ["message.posted", "message.corrected", "ask.sent", "ask.answered", "stance.changed"],
  },
  { id: "verify", label: "Verification", types: ["verification.result"] },
  { id: "options", label: "Options", types: ["option.evaluated", "options.final"] },
  {
    id: "decision",
    label: "Approval and actions",
    types: ["action.proposed", "approval.requested", "approval.granted", "approval.rejected", "action.executed"],
  },
  { id: "errors", label: "Errors", types: ["run.error"] },
];
const DEFAULT_GROUPS = GROUPS.map((g) => g.id).filter((id) => id !== "facts" && id !== "agents");
const PAGE = 300;

function agentOf(e: RunEvent): string {
  const p = e.payload as Record<string, unknown>;
  const a = p.agent ?? p.from ?? p.proposed_by;
  return typeof a === "string" ? a : "";
}

function toolCallOf(e: RunEvent): string | null {
  const p = e.payload as Record<string, unknown>;
  return typeof p.tool_call_id === "string" ? p.tool_call_id : null;
}

/** One line per event. Values are shown as they arrived. */
function describe(e: RunEvent): string {
  switch (e.type) {
    case "run.started":
      return `${e.payload.context.change_type} (${e.payload.context.mode})`;
    case "stage.started":
    case "stage.completed":
      return e.payload.stage;
    case "agent.active":
      return `turn starts (${e.payload.model})`;
    case "agent.idle":
      return `${e.payload.status} after ${e.payload.steps} steps${e.payload.error ? `: ${e.payload.error}` : ""}`;
    case "llm.call":
      return `${e.payload.model} · ${formatNumber(e.payload.prompt_tokens)} in / ${formatNumber(
        e.payload.completion_tokens,
      )} out · ${formatNumber(e.payload.latency_ms)} ms${e.payload.tool_calls.length ? ` · calls ${e.payload.tool_calls.join(", ")}` : ""}`;
    case "tool.called":
      return `${e.payload.tool_call_id} ${e.payload.tool}(${JSON.stringify(e.payload.args)})`;
    case "tool.result":
      return `${e.payload.tool_call_id} ${e.payload.tool} ${e.payload.ok ? `ok, ${e.payload.fact_ids.length} facts` : `error: ${e.payload.error}`}`;
    case "fact.registered":
      return `${e.payload.fact_id} = ${String(e.payload.value)} ${e.payload.unit} (${e.payload.tool}.${e.payload.path})`;
    case "message.posted":
      return `${e.payload.message_id} to ${agentLabel(e.payload.to)} [${e.payload.intent}] ${e.payload.content.slice(0, 120)}`;
    case "verification.result":
      return `${e.payload.message_id} ${e.payload.status}${e.payload.unresolved ? " (unresolved)" : ""}, ${e.payload.claims_checked} claims`;
    case "message.corrected":
      return `${e.payload.original_message_id} replaced by ${e.payload.corrected_message_id}`;
    case "ask.sent":
      return `asks ${agentLabel(e.payload.to)}: ${e.payload.question.slice(0, 120)}`;
    case "ask.answered":
      return `answered ${agentLabel(e.payload.to)} (${e.payload.answer_message_id ?? "no answer"})`;
    case "stance.changed":
      return `${e.payload.from ?? "none"} → ${e.payload.to} (${e.payload.when})`;
    case "option.evaluated":
      return e.payload.option_id;
    case "options.final":
      return `presented ${e.payload.options.map((o) => o.option_id).join(", ")}`;
    case "action.proposed":
      return `${e.payload.action_id} ${e.payload.type}`;
    case "approval.requested":
      return `options ${e.payload.options.join(", ")}`;
    case "approval.granted":
      return `${e.payload.option_id} by ${e.payload.approver_name} (${e.payload.approver_role})`;
    case "approval.rejected":
      return `by ${e.payload.approver_name}: ${e.payload.reason}`;
    case "action.executed":
      return `${e.payload.action_id} wrote ${e.payload.files.join(", ")}`;
    case "run.completed":
      return e.payload.status;
    case "run.error":
      return `${e.payload.fatal ? "fatal: " : ""}${e.payload.error}`;
    default:
      return "";
  }
}

interface TraceDrawerProps {
  open: boolean;
  focusToolCall: string | null;
  onClose: () => void;
  onClearFocus: () => void;
}

/** Full event log with filters, model use per call, and a download of the trace (SPEC 12.2). */
export function TraceDrawer({ open, focusToolCall, onClose, onClearFocus }: TraceDrawerProps) {
  const { state } = useRoom();
  const [groups, setGroups] = useState<string[]>(DEFAULT_GROUPS);
  const [agent, setAgent] = useState("");
  const [search, setSearch] = useState("");
  const [limit, setLimit] = useState(PAGE);
  const [expanded, setExpanded] = useState<string | null>(null);

  const types = useMemo(() => new Set(GROUPS.filter((g) => groups.includes(g.id)).flatMap((g) => g.types)), [groups]);
  const start = state.events[0]?.ts ? Date.parse(state.events[0].ts) : 0;

  const rows = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return state.events.filter((e) => {
      if (focusToolCall) return toolCallOf(e) === focusToolCall;
      if (!types.has(e.type)) return false;
      if (agent && agentOf(e) !== agent) return false;
      return !needle || `${e.type} ${describe(e)}`.toLowerCase().includes(needle);
    });
  }, [state.events, types, agent, search, focusToolCall]);

  const shown = rows.slice(-limit);
  const llm = state.events.filter((e): e is Extract<RunEvent, { type: "llm.call" }> => e.type === "llm.call");
  const models = [...new Set(llm.map((e) => e.payload.model))];
  const latency = llm.reduce((sum, e) => sum + e.payload.latency_ms, 0);

  const download = () => {
    const text = state.events.map((e) => JSON.stringify(e)).join("\n") + "\n";
    const url = URL.createObjectURL(new Blob([text], { type: "application/x-ndjson" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `${state.runId ?? "run"}-events.jsonl`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <AnimatePresence>
      {open ? (
        <motion.aside
          key="trace"
          initial={{ x: 720 }}
          animate={{ x: 0 }}
          exit={{ x: 720 }}
          transition={{ type: "tween", duration: 0.2 }}
          className="fixed top-0 right-0 bottom-0 z-40 flex w-[680px] flex-col border-l border-border bg-bg shadow-2xl"
          aria-label="Trace"
        >
          <div className="flex items-center justify-between border-b border-border px-5 py-3">
            <div>
              <h2 className="text-base">Trace</h2>
              <p className="text-xs text-text-muted">Every event of this run, as stored in its events file.</p>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={download}
                disabled={state.events.length === 0}
                className="rounded-full bg-accent px-3 py-1 text-xs font-semibold text-white disabled:opacity-40"
              >
                Download trace
              </button>
              <button type="button" onClick={onClose} className="text-text-muted hover:text-accent" aria-label="Close trace">
                ✕
              </button>
            </div>
          </div>

          <dl className="grid grid-cols-4 gap-2 border-b border-border px-5 py-3 text-xs">
            <div>
              <dt className="text-text-muted">Events</dt>
              <dd className="font-bold text-accent">{formatNumber(state.events.length)}</dd>
            </div>
            <div>
              <dt className="text-text-muted">Model calls</dt>
              <dd className="font-bold text-accent">{formatNumber(state.llm.calls)}</dd>
            </div>
            <div>
              <dt className="text-text-muted">Tokens in / out</dt>
              <dd className="font-bold text-accent">
                {formatNumber(state.llm.promptTokens)} / {formatNumber(state.llm.completionTokens)}
              </dd>
            </div>
            <div>
              <dt className="text-text-muted">Model time</dt>
              <dd className="font-bold text-accent">{formatNumber(latency / 1000)} s</dd>
            </div>
            <div className="col-span-4 text-text-muted">Models: {models.join(", ") || "none yet"}</div>
          </dl>

          <div className="flex flex-col gap-2 border-b border-border px-5 py-3 text-xs">
            {focusToolCall ? (
              <div className="flex items-center justify-between rounded bg-accent-tint px-3 py-2 text-accent">
                <span>
                  Showing tool call <strong>{focusToolCall}</strong> and the facts it registered.
                </span>
                <button type="button" onClick={onClearFocus} className="font-semibold">
                  Show all events
                </button>
              </div>
            ) : (
              <>
                <div className="flex flex-wrap gap-1">
                  {GROUPS.map((g) => {
                    const on = groups.includes(g.id);
                    return (
                      <button
                        key={g.id}
                        type="button"
                        aria-pressed={on}
                        onClick={() => setGroups((old) => (on ? old.filter((x) => x !== g.id) : [...old, g.id]))}
                        className={`rounded-full border px-2 py-0.5 ${on ? "border-accent bg-accent-tint text-accent" : "border-border text-text-muted"}`}
                      >
                        {g.label}
                      </button>
                    );
                  })}
                </div>
                <div className="flex gap-2">
                  <select
                    value={agent}
                    onChange={(e) => setAgent(e.target.value)}
                    className="rounded border border-border px-2 py-1"
                    aria-label="Agent"
                  >
                    <option value="">All agents</option>
                    {["intake", "contract", "cost", "time", "commercial", "verifier", "moderator", "orchestrator"].map((a) => (
                      <option key={a} value={a}>
                        {agentLabel(a)}
                      </option>
                    ))}
                  </select>
                  <input
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Search events, for example F-0012 or run_cpm"
                    className="flex-1 rounded border border-border px-2 py-1"
                    aria-label="Search events"
                  />
                </div>
              </>
            )}
            <div className="text-text-muted">
              {formatNumber(rows.length)} matching event{rows.length === 1 ? "" : "s"}
              {rows.length > shown.length ? `, showing the latest ${formatNumber(shown.length)}` : ""}
            </div>
          </div>

          <ol className="min-h-0 flex-1 overflow-y-auto px-3 py-2 font-mono text-[11px]">
            {rows.length > shown.length ? (
              <li className="py-1 text-center">
                <button type="button" onClick={() => setLimit((n) => n + PAGE)} className="text-accent underline">
                  Show {formatNumber(Math.min(PAGE, rows.length - shown.length))} earlier events
                </button>
              </li>
            ) : null}
            {shown.map((e) => {
              const isOpen = expanded === e.event_id;
              const seconds = start ? (Date.parse(e.ts) - start) / 1000 : 0;
              return (
                <li key={e.event_id} className="border-b border-surface-2">
                  <button
                    type="button"
                    onClick={() => setExpanded(isOpen ? null : e.event_id)}
                    className={`grid w-full grid-cols-[62px_56px_150px_70px_1fr] gap-2 px-2 py-1 text-left hover:bg-surface ${
                      e.type === "run.error" ? "text-alert" : ""
                    }`}
                  >
                    <span className="text-text-muted">{e.event_id.replace("E-", "")}</span>
                    <span className="text-text-muted">{seconds.toFixed(1)} s</span>
                    <span className="font-semibold text-accent">{e.type}</span>
                    <span>{agentLabel(agentOf(e))}</span>
                    <span className="truncate">{describe(e)}</span>
                  </button>
                  {isOpen ? (
                    <pre className="mx-2 mb-2 max-h-80 overflow-auto rounded bg-surface p-2 whitespace-pre-wrap">
                      {JSON.stringify(e, null, 2)}
                    </pre>
                  ) : null}
                </li>
              );
            })}
          </ol>
        </motion.aside>
      ) : null}
    </AnimatePresence>
  );
}
