import { citedClauses } from "../../state/runStore";
import { useRoom } from "../../state/RoomContext";
import { ClauseChip } from "../common/Chips";

/** Contract clauses the agents have cited so far. */
export function Clauses() {
  const { state } = useRoom();
  const cited = citedClauses(state);
  if (cited.length === 0) return <p className="text-xs text-text-muted">No clauses cited yet.</p>;
  return (
    <div className="flex flex-wrap gap-1.5">
      {cited.map((c) => (
        <ClauseChip key={c} clause={c} />
      ))}
    </div>
  );
}
