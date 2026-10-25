import { CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from "recharts";
import type { OptionResult } from "../../api/events";
import { aed, describeOption, formatAed, workingDays } from "../../format";
import { useRoom } from "../../state/RoomContext";
import { LoadingState } from "../layout/Panel";

interface Point {
  id: string;
  delay: number;
  cost: number;
}

function toPoint(o: OptionResult): Point {
  return { id: o.option_id, delay: o.delay_working_days, cost: o.total_cost_aed };
}

function PointTooltip({ active, payload }: { active?: boolean; payload?: { payload: Point }[] }) {
  const p = active ? payload?.[0]?.payload : undefined;
  if (!p) return null;
  return (
    <div className="rounded border border-border bg-bg px-2 py-1 text-xs shadow">
      <div className="font-semibold text-accent">{p.id}</div>
      <div>{describeOption(p.id)}</div>
      <div>
        {workingDays(p.delay)} delay · {aed(p.cost)}
      </div>
    </div>
  );
}

/** Total cost against delay for every option evaluated in this run; the Pareto set highlighted. */
export function OptionsPanel() {
  const { state } = useRoom();
  const all = Object.values(state.options);
  if (all.length === 0) return <LoadingState message="No options evaluated yet" />;
  const pareto = new Set(state.results.searchOptions?.pareto_option_ids ?? []);
  const front = all.filter((o) => pareto.has(o.option_id)).map(toPoint);
  const rest = all.filter((o) => !pareto.has(o.option_id)).map(toPoint);

  return (
    <div className="flex flex-col gap-3 text-sm">
      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 10, right: 16, bottom: 24, left: 8 }}>
            <CartesianGrid stroke="var(--surface-2)" />
            <XAxis
              type="number"
              dataKey="delay"
              name="Delay"
              allowDecimals={false}
              tick={{ fontSize: 10, fill: "var(--text-muted)" }}
              label={{ value: "Delay (working days)", position: "insideBottom", offset: -12, fontSize: 10, fill: "var(--text-muted)" }}
            />
            <YAxis
              type="number"
              dataKey="cost"
              name="Total cost"
              width={58}
              tick={{ fontSize: 9, fill: "var(--text-muted)" }}
              tickFormatter={(v: number) => formatAed(v)}
            />
            <ZAxis range={[70, 70]} />
            <Tooltip content={<PointTooltip />} />
            <Scatter name="Other options" data={rest} fill="var(--border)" />
            <Scatter name="Pareto options" data={front} fill="var(--accent)" />
          </ScatterChart>
        </ResponsiveContainer>
      </div>
      <p className="text-xs text-text-muted">
        Dark points are not beaten on both cost and delay by any other option (the Pareto set). Total cost in AED.
      </p>
      {pareto.size ? (
        <table className="w-full text-xs">
          <thead className="text-left text-text-muted">
            <tr>
              <th className="py-1">Option</th>
              <th className="py-1 text-right">Delay</th>
              <th className="py-1 text-right">Total cost</th>
            </tr>
          </thead>
          <tbody>
            {all
              .filter((o) => pareto.has(o.option_id))
              .map((o) => (
                <tr key={o.option_id} className="border-t border-border">
                  <td className="py-1 font-semibold text-accent">{o.option_id}</td>
                  <td className="py-1 text-right">{workingDays(o.delay_working_days)}</td>
                  <td className="py-1 text-right">{aed(o.total_cost_aed)}</td>
                </tr>
              ))}
          </tbody>
        </table>
      ) : null}
    </div>
  );
}
