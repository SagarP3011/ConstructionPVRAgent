import type { OptionResult } from "../../api/events";
import type { RunState } from "../../state/runStore";

/** The options worth showing: the final presented options, else the Pareto set, else all evaluated. */
export function focusOptions(state: RunState): OptionResult[] {
  if (state.finalOptions?.length) return state.finalOptions;
  const pareto = state.results.searchOptions?.pareto_option_ids ?? [];
  const fromPareto = pareto.map((id) => state.options[id]).filter((o): o is OptionResult => Boolean(o));
  if (fromPareto.length) return fromPareto;
  return Object.values(state.options);
}
