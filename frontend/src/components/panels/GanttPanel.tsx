import type { CpmActivity } from "../../api/events";
import { formatDate, workingDays } from "../../format";
import { useRoom } from "../../state/RoomContext";
import { LoadingState } from "../layout/Panel";

const WIDTH = 540;
const LABEL_W = 150;
const ROW_H = 22;
const TOP = 34;
const RIGHT_PAD = 26;

/**
 * Critical path and the affected chain: baseline against impacted bars (without extra crews), float
 * shading, and markers for contract completion, impacted completion and the Employer's commitment.
 * Positions are drawn from ES, EF and TF in the CPM results; nothing is calculated here.
 */
export function GanttPanel() {
  const { state, project } = useRoom();
  const baseline = state.results.baselineCpm;
  const impacted = state.results.impactedCpm;
  const added = state.results.addedDuration;
  if (!baseline && !impacted) return <LoadingState message="The Time agent is working on the programme" />;

  const addedDays = Object.fromEntries((added?.activities ?? []).map((a) => [a.activity_id, a.added_days]));
  const main = impacted ?? baseline;
  if (!main) return null;
  const rowIds = Object.values(main.activities)
    .filter((a) => a.critical || a.activity_id in addedDays || baseline?.activities[a.activity_id]?.critical)
    .sort((a, b) => (baseline?.activities[a.activity_id]?.ES ?? a.ES) - (baseline?.activities[b.activity_id]?.ES ?? b.ES) || a.activity_id.localeCompare(b.activity_id))
    .map((a) => a.activity_id);

  const timeOverride = state.context?.overrides.time_buffer_working_days ?? null;
  const commitment = project && timeOverride === null ? project.employer_commitment_working_day : null;
  const lastDay = Math.max(
    main.completion_working_day,
    baseline?.completion_working_day ?? 0,
    commitment ?? 0,
    ...rowIds.map((id) => {
      const a = main.activities[id];
      return a ? a.EF + a.TF : 0;
    }),
  );
  const scale = (WIDTH - LABEL_W - RIGHT_PAD) / (lastDay + 2);
  const x = (day: number) => LABEL_W + day * scale;
  const height = TOP + rowIds.length * ROW_H + 30;
  const ticks = Array.from({ length: Math.floor((lastDay + 2) / 10) + 1 }, (_, i) => i * 10);
  const late = commitment !== null && impacted !== null && impacted.completion_working_day > commitment;

  const marker = (day: number, label: string, colour: string, dashed: boolean, row: number) => (
    <g key={label}>
      <line
        x1={x(day)}
        x2={x(day)}
        y1={TOP - 6}
        y2={height - 22}
        stroke={colour}
        strokeWidth={1.5}
        strokeDasharray={dashed ? "4 3" : undefined}
      />
      <text x={x(day)} y={height - 12 + row * 10} textAnchor="middle" fontSize={9} fill={colour} fontWeight={600}>
        {label}
      </text>
    </g>
  );

  return (
    <div className="flex flex-col gap-3 text-sm">
      <div className="grid grid-cols-2 gap-2 text-xs">
        {baseline ? (
          <div className="rounded-card bg-surface p-2">
            <div className="text-text-muted">Contract completion (baseline)</div>
            <div className="font-bold text-accent">
              day {baseline.completion_working_day}, {formatDate(baseline.completion_date)}
            </div>
          </div>
        ) : null}
        {impacted ? (
          <div className={`rounded-card p-2 ${late ? "border border-alert" : "bg-accent-tint"}`}>
            <div className="text-text-muted">With the change, no extra crews</div>
            <div className={`font-bold ${late ? "text-alert" : "text-accent"}`}>
              day {impacted.completion_working_day}, {formatDate(impacted.completion_date)}
            </div>
          </div>
        ) : null}
      </div>

      <svg viewBox={`0 0 ${WIDTH} ${height + 10}`} className="w-full" role="img" aria-label="Gantt chart of the critical path and the affected activities">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={TOP - 10} y2={height - 22} stroke="var(--surface-2)" />
            <text x={x(t)} y={TOP - 14} textAnchor="middle" fontSize={8} fill="var(--text-muted)">
              {t}
            </text>
          </g>
        ))}
        <text x={LABEL_W} y={10} fontSize={8} fill="var(--text-muted)">
          working day
        </text>

        {rowIds.map((id, i) => {
          const a: CpmActivity | undefined = main.activities[id];
          const b = baseline?.activities[id];
          if (!a) return null;
          const y = TOP + i * ROW_H;
          const plus = addedDays[id];
          return (
            <g key={id}>
              <title>
                {`${id} ${a.name}: ${formatDate(a.start_date)} to ${formatDate(a.finish_date)}, float ${a.TF}`}
              </title>
              <text x={4} y={y + 12} fontSize={9} fill="var(--text)" fontWeight={plus ? 700 : 400}>
                {id} {a.name.length > 20 ? `${a.name.slice(0, 19)}…` : a.name}
              </text>
              {b && impacted ? (
                <rect x={x(b.ES)} y={y + 14} width={Math.max(1, x(b.EF) - x(b.ES))} height={3} rx={1.5} fill="var(--text-muted)" opacity={0.45} />
              ) : null}
              {a.TF > 0 ? (
                <rect
                  x={x(a.EF)}
                  y={y + 3}
                  width={x(a.EF + a.TF) - x(a.EF)}
                  height={9}
                  fill="var(--accent-tint)"
                  stroke="var(--accent-2)"
                  strokeDasharray="2 2"
                  strokeWidth={0.6}
                />
              ) : null}
              <rect
                x={x(a.ES)}
                y={y + 3}
                width={Math.max(1, x(a.EF) - x(a.ES))}
                height={9}
                rx={2}
                fill={a.critical ? "var(--accent)" : "var(--accent-2)"}
              />
              {plus ? (
                <text x={x(a.EF + a.TF) + 3} y={y + 11} fontSize={8} fontWeight={700} fill="var(--accent)">
                  +{plus}
                </text>
              ) : null}
            </g>
          );
        })}

        {baseline ? marker(baseline.completion_working_day, "contract", "var(--text-muted)", true, 0) : null}
        {impacted ? marker(impacted.completion_working_day, "impacted", late ? "var(--alert)" : "var(--accent)", false, 1) : null}
        {commitment !== null ? marker(commitment, "commitment", "var(--accent-2)", true, 0) : null}
      </svg>

      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-text-muted">
        <li className="flex items-center gap-1">
          <span className="inline-block h-2 w-4 rounded-sm bg-accent" /> critical
        </li>
        <li className="flex items-center gap-1">
          <span className="inline-block h-2 w-4 rounded-sm bg-accent-2" /> has float
        </li>
        <li className="flex items-center gap-1">
          <span className="inline-block h-2 w-4 border border-dashed border-accent-2 bg-accent-tint" /> float
        </li>
        {impacted && baseline ? (
          <li className="flex items-center gap-1">
            <span className="inline-block h-1 w-4 rounded-sm bg-text-muted opacity-50" /> baseline
          </li>
        ) : null}
        {project && commitment !== null ? (
          <li>
            Employer commitment: {formatDate(project.employer_commitment_date)}
          </li>
        ) : null}
      </ul>

      {added ? (
        <div className="rounded-card bg-surface p-2 text-xs">
          <div className="mb-1 font-semibold">Added duration from the change</div>
          <ul>
            {added.activities.map((a) => (
              <li key={a.activity_id} className="flex justify-between">
                <span>
                  {a.activity_id} {a.name}
                </span>
                <span>
                  {a.baseline_duration} → <strong className="text-accent">{a.new_duration}</strong> (+{workingDays(a.added_days)})
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
