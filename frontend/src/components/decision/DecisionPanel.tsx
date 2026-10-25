import { useEffect, useState } from "react";
import { api } from "../../api/client";
import type { Action } from "../../api/events";
import { aed, describeOption } from "../../format";
import { agentLabel, DEBATERS } from "../../state/agents";
import { useRoom } from "../../state/RoomContext";
import { AgentTag } from "../common/AgentIcon";
import { LoadingState, Panel } from "../layout/Panel";
import { ApprovalModal, type ModalKind } from "./ApprovalModal";
import { OptionCard } from "./OptionCard";

const ACTION_LABEL: Record<string, string> = {
  draft_pvr_form: "Draft the PVR output form",
  draft_verification_report: "Draft the verification report",
  create_task: "Create a task",
  notify: "Send notifications",
};

function actionDetail(a: Action): string {
  const p = a.payload;
  if (a.type === "create_task") return [p.title, p.owner ? `owner: ${String(p.owner)}` : ""].filter(Boolean).join(" · ");
  if (a.type === "notify" && Array.isArray(p.recipients)) return `to ${p.recipients.join(", ")}`;
  return "";
}

/** Stage 6: a named person chooses one option and the actions to execute, then approves or rejects. */
export function DecisionPanel() {
  const { state, isReplay } = useRoom();
  const [choice, setChoice] = useState<string | null>(null);
  const [ticked, setTicked] = useState<string[]>([]);
  const [name, setName] = useState("");
  const [role, setRole] = useState("");
  const [modal, setModal] = useState<ModalKind | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const decided = state.decision;
  const options = state.finalOptions ?? [];
  const actions = state.actionOrder.map((id) => state.actions[id]).filter((a): a is Action => Boolean(a));
  const waiting = state.status === "awaiting_approval" && !decided;
  const canDecide = waiting && !isReplay;

  // Tick every proposed action by default once the request arrives.
  useEffect(() => {
    if (state.approvalRequested) setTicked(state.actionOrder);
  }, [state.approvalRequested, state.actionOrder]);

  if (!state.approvalRequested && !decided) {
    return (
      <Panel title="Decision">
        <LoadingState message="The options are prepared for a person to decide after the debate." />
      </Panel>
    );
  }

  const chosenId = decided && decided.status === "approved" ? decided.option_id : null;
  const selected = options.find((o) => o.option_id === choice);
  const summary = selected
    ? [
        `Option ${selected.option_id}: ${describeOption(selected.option_id)}, total ${aed(selected.total_cost_aed)}.`,
        `Actions: ${ticked.length ? ticked.map((id) => `${id} ${ACTION_LABEL[state.actions[id]?.type ?? ""] ?? ""}`).join("; ") : "none"}.`,
        `Approver: ${name} (${role}).`,
      ]
    : [`Rejected by ${name} (${role}). Nothing will be executed.`];

  const confirm = async (reason: string) => {
    if (!state.runId) return;
    setBusy(true);
    setError(null);
    try {
      if (modal === "approve" && choice) {
        await api.approve(state.runId, { option_id: choice, action_ids: ticked, approver_name: name, approver_role: role });
      } else if (modal === "reject") {
        await api.reject(state.runId, { approver_name: name, approver_role: role, reason });
      }
      setModal(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "The decision could not be recorded");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel
      title="Decision"
      right={
        <span className="text-xs text-text-muted">
          {waiting && isReplay ? "Replay: the recorded decision follows" : waiting ? "Waiting for your decision" : ""}
        </span>
      }
    >
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-3 text-xs">
          <span className="text-text-muted">Final stances:</span>
          {DEBATERS.map((a) => (
            <span key={a} className="inline-flex items-center gap-1">
              <AgentTag agent={a} size={12} />
              <strong className="text-accent">{state.finalStances[a] ?? state.agents[a].stance ?? "none"}</strong>
            </span>
          ))}
          {state.debate ? (
            <span className="text-text-muted">
              · debate ended after {state.debate.rounds} round{state.debate.rounds === 1 ? "" : "s"} (
              {state.debate.stopReason.replace(/_/g, " ")})
            </span>
          ) : null}
        </div>

        <div className="grid gap-3" style={{ gridTemplateColumns: `repeat(${Math.max(1, Math.min(3, options.length))}, minmax(0, 1fr))` }}>
          {options.map((o) => (
            <OptionCard
              key={o.option_id}
              option={o}
              selected={choice === o.option_id}
              chosen={chosenId === o.option_id}
              disabled={!canDecide}
              onSelect={() => setChoice(o.option_id)}
            />
          ))}
        </div>

        <div className="grid grid-cols-[3fr_2fr] gap-4">
          <fieldset className="flex flex-col gap-2 text-sm">
            <legend className="mb-1 font-semibold">Actions to execute on approval</legend>
            {actions.map((a) => (
              <label key={a.action_id} className="flex items-start gap-2">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={canDecide ? ticked.includes(a.action_id) : a.status === "approved" || a.status === "executed"}
                  disabled={!canDecide}
                  onChange={(e) =>
                    setTicked((old) => (e.target.checked ? [...old, a.action_id] : old.filter((x) => x !== a.action_id)))
                  }
                />
                <span>
                  <span className="font-semibold">
                    {a.action_id} {ACTION_LABEL[a.type] ?? a.type}
                  </span>
                  {actionDetail(a) ? <span className="text-text-muted"> · {actionDetail(a)}</span> : null}
                  <span className="block text-xs text-text-muted">
                    Proposed by {agentLabel(a.proposed_by)}: {a.reason}
                  </span>
                  {!canDecide && a.status !== "pending" ? (
                    <span className="text-[11px] font-semibold text-accent">{a.status.replace("_", " ")}</span>
                  ) : null}
                </span>
              </label>
            ))}
          </fieldset>

          {decided ? (
            <div className="rounded-card bg-surface p-4 text-sm">
              <div className="mb-1 font-semibold text-accent">
                {decided.status === "approved" ? `Approved ${decided.option_id}` : "Rejected"}
              </div>
              <div>
                by {decided.approver_name}, {decided.approver_role}
              </div>
              {decided.status === "rejected" ? <div className="mt-1 text-text-muted">Reason: {decided.reason}</div> : null}
            </div>
          ) : canDecide ? (
            <div className="flex flex-col gap-2 text-sm">
              <label className="flex flex-col gap-1">
                <span className="font-semibold">Your name</span>
                <input value={name} onChange={(e) => setName(e.target.value)} className="rounded border border-border px-2 py-1.5" />
              </label>
              <label className="flex flex-col gap-1">
                <span className="font-semibold">Your role</span>
                <input
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                  placeholder="for example Project Director"
                  className="rounded border border-border px-2 py-1.5"
                />
              </label>
              <div className="mt-2 flex gap-2">
                <button
                  type="button"
                  onClick={() => setModal("approve")}
                  disabled={!choice || !name.trim() || !role.trim()}
                  className="flex-1 rounded-full bg-accent px-4 py-2 font-semibold text-white disabled:opacity-40"
                >
                  Approve
                </button>
                <button
                  type="button"
                  onClick={() => setModal("reject")}
                  disabled={!name.trim() || !role.trim()}
                  className="rounded-full border border-accent px-4 py-2 font-semibold text-accent disabled:opacity-40"
                >
                  Reject
                </button>
              </div>
              {!choice ? <p className="text-xs text-text-muted">Choose an option above.</p> : null}
            </div>
          ) : (
            <LoadingState message="Waiting for the recorded decision" />
          )}
        </div>
      </div>
      <ApprovalModal
        kind={modal}
        summary={modal === "reject" ? [`Rejected by ${name} (${role}). Nothing will be executed.`] : summary}
        busy={busy}
        error={error}
        onConfirm={(reason) => void confirm(reason)}
        onCancel={() => {
          setModal(null);
          setError(null);
        }}
      />
    </Panel>
  );
}
