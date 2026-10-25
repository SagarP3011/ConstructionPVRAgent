import type { AgentId, FinalOption } from "../../api/events";
import { aed, describeOption, formatDate, workingDays } from "../../format";
import { AgentTag } from "../common/AgentIcon";

interface OptionCardProps {
  option: FinalOption;
  selected: boolean;
  chosen: boolean;
  disabled: boolean;
  onSelect: () => void;
}

/** One presented option with its schedule, cost, buffer and contingency, and the agents behind it. */
export function OptionCard({ option, selected, chosen, disabled, onSelect }: OptionCardProps) {
  const overBudget = option.contingency_remaining_aed < 0;
  const overTime = option.time_buffer_remaining_days < 0;
  return (
    <button
      type="button"
      onClick={onSelect}
      disabled={disabled}
      aria-pressed={selected}
      className={`flex flex-col gap-2 rounded-card border-2 p-4 text-left transition-colors ${
        selected || chosen ? "border-accent bg-accent-tint" : "border-border bg-bg hover:border-accent-2"
      } disabled:cursor-default`}
    >
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-base font-bold text-accent">{option.option_id}</span>
        {chosen ? <span className="rounded-full bg-accent px-2 py-0.5 text-[10px] font-semibold text-white">approved</span> : null}
      </div>
      <div className="text-xs text-text-muted">{describeOption(option.option_id)}</div>
      <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
        <dt className="text-text-muted">Delay</dt>
        <dd className="text-right font-bold">{workingDays(option.delay_working_days)}</dd>
        <dt className="text-text-muted">Completion</dt>
        <dd className="text-right font-bold">{formatDate(option.completion_date)}</dd>
        <dt className="text-text-muted">Total cost</dt>
        <dd className="text-right font-bold">{aed(option.total_cost_aed)}</dd>
        <dt className="text-text-muted">Time buffer left</dt>
        <dd className={`text-right font-bold ${overTime ? "text-alert" : ""}`}>
          {workingDays(option.time_buffer_remaining_days)}
        </dd>
        <dt className="text-text-muted">Contingency left</dt>
        <dd className={`text-right font-bold ${overBudget ? "text-alert" : ""}`}>{aed(option.contingency_remaining_aed)}</dd>
      </dl>
      {overBudget ? <div className="text-xs font-semibold text-alert">Needs a budget uplift</div> : null}
      <div className="mt-1 flex flex-wrap items-center gap-2 border-t border-border pt-2 text-xs">
        <span className="text-text-muted">Supported by</span>
        {option.supported_by.length ? (
          option.supported_by.map((a: AgentId) => <AgentTag key={a} agent={a} size={12} />)
        ) : (
          <span className="text-text-muted">no agent</span>
        )}
      </div>
    </button>
  );
}
