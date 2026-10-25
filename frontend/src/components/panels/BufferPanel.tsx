import { aed, describeOption, workingDays } from "../../format";
import { useRoom } from "../../state/RoomContext";
import { LoadingState } from "../layout/Panel";
import { focusOptions } from "./optionSets";

interface GaugeProps {
  label: string;
  remaining: number;
  total: number | null;
  text: string;
}

/** A bar showing how much of the buffer or contingency is left. Red when it is overrun. */
function Gauge({ label, remaining, total, text }: GaugeProps) {
  const over = remaining < 0;
  const share = total && total > 0 ? Math.max(0, Math.min(1, remaining / total)) : over ? 0 : 1;
  return (
    <div className="text-xs">
      <div className="flex justify-between">
        <span className="text-text-muted">{label}</span>
        <span className={`font-bold ${over ? "text-alert" : "text-accent"}`}>{text}</span>
      </div>
      <div className={`mt-1 h-2 overflow-hidden rounded-full ${over ? "bg-alert" : "bg-surface-2"}`}>
        {!over ? <div className="h-full rounded-full bg-accent" style={{ width: `${share * 100}%` }} /> : null}
      </div>
    </div>
  );
}

/** Time buffer and cost contingency left under each option. */
export function BufferPanel() {
  const { state, project } = useRoom();
  const options = focusOptions(state);
  if (options.length === 0) return <LoadingState message="The Commercial agent is checking the buffer and contingency" />;

  // Totals for the gauges: from a buffer check in this run, else the run's overrides, else the project data.
  const anyCheck = Object.values(state.results.buffers)[0];
  const overrides = state.context?.overrides;
  const timeTotal =
    anyCheck?.time_buffer_days ?? overrides?.time_buffer_working_days ?? project?.time_buffer_working_days ?? null;
  const costTotal =
    anyCheck?.contingency_aed ?? overrides?.cost_contingency_remaining_aed ?? project?.cost_contingency_remaining_aed ?? null;

  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-text-muted">
        Time buffer {timeTotal !== null ? workingDays(timeTotal) : ""} before the Employer's commitment; cost
        contingency {costTotal !== null ? aed(costTotal) : ""} for this package.
      </p>
      {options.map((o) => {
        const check = state.results.buffers[o.option_id];
        const uplift = check && check.budget_uplift_needed_aed > 0 ? check.budget_uplift_needed_aed : null;
        return (
          <div key={o.option_id} className="rounded-card border border-border p-3">
            <div className="mb-2 flex items-baseline justify-between">
              <span className="font-semibold text-accent">{o.option_id}</span>
              <span className="text-xs text-text-muted">{describeOption(o.option_id)}</span>
            </div>
            <div className="flex flex-col gap-2">
              <Gauge
                label="Time buffer left"
                remaining={o.time_buffer_remaining_days}
                total={timeTotal}
                text={workingDays(o.time_buffer_remaining_days)}
              />
              <Gauge
                label="Contingency left"
                remaining={o.contingency_remaining_aed}
                total={costTotal}
                text={aed(o.contingency_remaining_aed)}
              />
            </div>
            {o.contingency_remaining_aed < 0 ? (
              <p className="mt-2 text-xs font-semibold text-alert">
                Over the contingency: budget uplift needed{uplift !== null ? ` (${aed(uplift)})` : ""}.
              </p>
            ) : null}
            {o.time_buffer_remaining_days < 0 ? (
              <p className="mt-1 text-xs font-semibold text-alert">Breaks the Employer's commitment date.</p>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
