import { motion } from "framer-motion";
import { aed, formatDelta } from "../../format";
import { useRoom } from "../../state/RoomContext";

/** Affected BOQ lines as the agents find them; unaffected items greyed, review items flagged. */
export function BoqLines() {
  const { state } = useRoom();
  const q = state.results.quantities;
  const price = state.results.price;
  if (!q) {
    return <p className="text-xs text-text-muted">The Cost agent has not quantified the change yet.</p>;
  }
  const amounts = Object.fromEntries((price?.lines ?? []).map((l) => [l.code, l.amount_aed]));
  return (
    <ul className="flex flex-col gap-1.5 text-xs">
      {q.lines
        .filter((l) => l.delta !== 0)
        .map((l, i) => (
          <motion.li
            key={l.code}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.05 }}
            className="rounded border border-border p-2"
          >
            <div className="flex justify-between gap-2">
              <span className="font-mono font-semibold">{l.code}</span>
              <span className="font-bold text-accent">
                {formatDelta(l.delta)} {l.unit}
              </span>
            </div>
            <div className="text-text-muted">{l.description}</div>
            {l.code in amounts ? <div className="text-right font-semibold">{aed(amounts[l.code] ?? 0)}</div> : null}
          </motion.li>
        ))}
      {q.unaffected.map((u) => (
        <li key={u.code} className="rounded border border-dashed border-border p-2 text-text-muted opacity-70">
          <div className="flex justify-between gap-2">
            <span className="font-mono">{u.code}</span>
            <span>not affected</span>
          </div>
          <div>{u.reason}</div>
        </li>
      ))}
      {q.requires_review.map((r) => (
        <li key={r.code} className="rounded border border-accent-2 bg-accent-tint p-2">
          <div className="flex justify-between gap-2">
            <span className="font-mono font-semibold">{r.code}</span>
            <span className="font-semibold text-accent">{r.needs_new_rate ? "new rate needed" : "needs review"}</span>
          </div>
          <div className="text-text-muted">{r.description}</div>
          <div>{r.reason}</div>
        </li>
      ))}
    </ul>
  );
}
