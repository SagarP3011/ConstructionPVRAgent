import type { Claim } from "../../api/events";
import { formatValue } from "../../format";
import { useSelection } from "../../state/RoomContext";

/** A claim stated in a message: label, value and the fact it cites. Click to see the fact's source. */
export function ClaimChip({ claim }: { claim: Claim }) {
  const { selectFact, selectedFactId } = useSelection();
  const selected = selectedFactId === claim.fact_id;
  return (
    <button
      type="button"
      onClick={() => selectFact(selected ? null : claim.fact_id)}
      title="Show where this number comes from"
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] transition-colors ${
        selected ? "border-accent bg-accent text-white" : "border-border bg-surface text-text hover:border-accent-2"
      }`}
    >
      <span className={selected ? "" : "text-text-muted"}>{claim.label.replace(/_/g, " ")}</span>
      <span className="font-bold">{formatValue(claim.value, claim.unit)}</span>
      <span className="opacity-60">{claim.fact_id}</span>
    </button>
  );
}

/** An inline citation such as [F-0012] inside message text. */
export function FactRef({ factId }: { factId: string }) {
  const { selectFact, selectedFactId } = useSelection();
  const selected = selectedFactId === factId;
  return (
    <button
      type="button"
      onClick={() => selectFact(selected ? null : factId)}
      className={`mx-0.5 rounded px-1 align-baseline text-[10px] ${
        selected ? "bg-accent text-white" : "bg-accent-tint text-accent hover:bg-accent-2 hover:text-white"
      }`}
      title="Show where this number comes from"
    >
      {factId}
    </button>
  );
}

/** A contract clause reference. Click to read the clause. */
export function ClauseChip({ clause }: { clause: string }) {
  const { selectClause, selectedClause, contractClauses } = useSelection();
  const title = contractClauses.find((c) => c.clause === clause)?.title;
  const selected = selectedClause === clause;
  return (
    <button
      type="button"
      onClick={() => selectClause(selected ? null : clause)}
      className={`rounded-full border px-2.5 py-0.5 text-xs transition-colors ${
        selected ? "border-accent bg-accent text-white" : "border-border bg-bg text-accent hover:border-accent-2"
      }`}
    >
      <span className="font-semibold">{clause}</span>
      {title ? <span className={selected ? "" : "text-text-muted"}> {title}</span> : null}
    </button>
  );
}
