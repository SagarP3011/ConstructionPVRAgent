import { formatNumber } from "../../format";
import { useRoom } from "../../state/RoomContext";

/** Drawing revision (wall) or element parameter change (road, paving): old against new. */
export function DrawingDiff() {
  const { state } = useRoom();
  const d = state.results.drawing;
  if (!d) return null;
  return (
    <div className="text-sm">
      <div className="mb-1 text-xs font-semibold text-text-muted">
        {d.drawing ? `Drawing ${d.drawing}, revision ${d.from_revision}${d.to_revision ? ` to ${d.to_revision}` : ""}` : "Change"}
      </div>
      <table className="w-full text-xs">
        <tbody>
          {d.changes.map((c) => (
            <tr key={c.parameter} className="border-t border-border">
              <td className="py-1 pr-2">{c.parameter.replace(/_/g, " ")}</td>
              <td className="py-1 text-right text-text-muted line-through">
                {c.old === null ? "" : `${formatNumber(c.old)} ${c.unit}`}
              </td>
              <td className="py-1 text-right font-bold text-accent">
                {c.new === null ? "" : `${formatNumber(c.new)} ${c.unit}`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {d.to_revision_note ? <p className="mt-1 text-xs text-text-muted">{d.to_revision_note}</p> : null}
    </div>
  );
}
