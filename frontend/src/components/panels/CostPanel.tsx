import { aed, formatDelta, formatNumber, workingDays } from "../../format";
import { useRoom } from "../../state/RoomContext";
import { LoadingState } from "../layout/Panel";

/** Cost line breakdown at contract rates; in contractor PVR mode, claimed against assessed. */
export function CostPanel() {
  const { state } = useRoom();
  const price = state.results.price;
  const claim = state.results.claim;
  if (!price) return <LoadingState message="The Cost agent is pricing the change" />;
  const largest = Math.max(...price.lines.map((l) => Math.abs(l.amount_aed)), 1);

  return (
    <div className="flex flex-col gap-5 text-sm">
      <section>
        <div className="mb-2 flex items-baseline justify-between">
          <h3 className="text-sm">Direct cost at contract rates</h3>
          <span className="text-lg font-bold text-accent">{aed(price.direct_cost_aed)}</span>
        </div>
        <ul className="flex flex-col gap-2">
          {price.lines
            .filter((l) => l.delta !== 0)
            .map((l) => (
              <li key={l.code} className="text-xs">
                <div className="flex justify-between gap-2">
                  <span>
                    <span className="font-mono font-semibold">{l.code}</span> {l.description}
                  </span>
                  <span className="font-bold whitespace-nowrap">{aed(l.amount_aed)}</span>
                </div>
                <div className="mt-0.5 flex items-center gap-2 text-text-muted">
                  <span className="h-1.5 rounded-full bg-accent" style={{ width: `${(Math.abs(l.amount_aed) / largest) * 60}%` }} />
                  <span className="whitespace-nowrap">
                    {formatDelta(l.delta)} {l.unit} × AED {formatNumber(l.rate_aed)}
                  </span>
                </div>
              </li>
            ))}
        </ul>
        <p className="mt-2 text-xs text-text-muted">Rates: {price.rate_source}.</p>
        {price.unpriced_items.length ? (
          <div className="mt-3 rounded-card border border-accent-2 bg-accent-tint p-2 text-xs">
            <div className="font-semibold text-accent">Not priced (flagged, never guessed)</div>
            <ul className="mt-1 list-disc pl-4">
              {price.unpriced_items.map((u) => (
                <li key={u.code}>
                  <span className="font-mono">{u.code}</span> {u.reason}
                  {u.needs_new_rate ? " (a new rate must be agreed)" : ""}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>

      {claim ? (
        <section>
          <h3 className="mb-2 text-sm">
            Contractor claim {claim.pvr_ref}: claimed against assessed
          </h3>
          <table className="w-full text-xs">
            <thead className="text-left text-text-muted">
              <tr>
                <th className="py-1 pr-1">Item</th>
                <th className="py-1 pr-1 text-right">Claimed</th>
                <th className="py-1 text-right">Assessed</th>
              </tr>
            </thead>
            <tbody>
              {claim.lines.map((l) => (
                <tr key={l.claimed_description} className="border-t border-border align-top">
                  <td className="py-1 pr-1">
                    {l.claimed_description}
                    <div className="text-text-muted">
                      rate AED {formatNumber(l.claimed_rate_aed)}
                      {l.boq_rate_aed !== null ? ` claimed, AED ${formatNumber(l.boq_rate_aed)} BOQ` : ""} · clause {l.clause}
                    </div>
                  </td>
                  <td className="py-1 pr-1 text-right">{aed(l.claimed_amount_aed)}</td>
                  <td className="py-1 text-right font-semibold text-accent">
                    {l.assessed_amount_aed === null ? "not allowed" : aed(l.assessed_amount_aed)}
                  </td>
                </tr>
              ))}
              <tr className="border-t border-border">
                <td className="py-1 pr-1">Preliminaries {formatNumber(claim.claimed_preliminaries_percent)}%</td>
                <td className="py-1 pr-1 text-right">{aed(claim.claimed_preliminaries_aed)}</td>
                <td className="py-1 text-right font-semibold text-accent">{aed(claim.allowed_preliminaries_aed)}</td>
              </tr>
              <tr className="border-t-2 border-accent font-bold">
                <td className="py-1 pr-1">Total</td>
                <td className="py-1 pr-1 text-right">{aed(claim.claimed_total_aed)}</td>
                <td className="py-1 text-right text-accent">{aed(claim.assessed_direct_cost_aed)}</td>
              </tr>
              <tr className="border-t border-border">
                <td className="py-1 pr-1">Extension of time</td>
                <td className="py-1 pr-1 text-right">{workingDays(claim.claimed_extension_days)}</td>
                <td className="py-1 text-right font-semibold text-accent">
                  {workingDays(claim.assessed_extension_days_without_acceleration)}
                </td>
              </tr>
            </tbody>
          </table>
          <p className="mt-2 text-xs text-text-muted">
            Difference in direct cost: <strong className="text-text">{aed(claim.difference_direct_aed)}</strong>
          </p>
          <h4 className="mt-3 mb-1 text-xs font-semibold text-accent">Adjustments and the clauses behind them</h4>
          <ul className="flex flex-col gap-1 text-xs">
            {claim.adjustments.map((a) => (
              <li key={a.item} className="rounded bg-surface px-2 py-1">
                <div className="flex justify-between gap-2">
                  <span className="font-semibold">{a.item}</span>
                  <span className="whitespace-nowrap">
                    {formatNumber(a.claimed)} → <strong className="text-accent">{formatNumber(a.assessed)}</strong> {a.unit}
                  </span>
                </div>
                <div className="text-text-muted">
                  Clause {a.clause}: {a.reason}
                </div>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
