import type {
  AddedDurationResult,
  BufferResult,
  ChangeRequestResult,
  ClaimComparisonResult,
  ClauseResult,
  CpmResult,
  DrawingComparisonResult,
  NoticeResult,
  OptionResult,
  PriceResult,
  QuantifyResult,
  SearchOptionsResult,
} from "../../api/events";
import { aed, formatDate, workingDays } from "../../format";
import type { ToolCallView } from "../../state/runStore";

/** One line saying what a tool call returned, for the timeline ("completion day 95, Fri 12 Feb 2027").
 * It only reads values from the result. */
export function toolSummary(call: ToolCallView): string {
  if (call.ok === null) return "running…";
  if (!call.ok) return `error: ${call.error}`;
  const r = call.result;
  switch (call.tool) {
    case "get_change_request":
      return (r as ChangeRequestResult).id;
    case "compare_drawing_revisions": {
      const d = r as DrawingComparisonResult;
      return d.drawing ? `drawing ${d.drawing} revision ${d.from_revision} to ${d.to_revision ?? "?"}` : "element geometry";
    }
    case "check_notice": {
      const n = r as NoticeResult;
      return `${n.calendar_days} calendar days, ${n.within_limit ? "within" : "outside"} ${n.limit_days}`;
    }
    case "quantify_change": {
      const q = r as QuantifyResult;
      const changed = q.lines.filter((l) => l.delta !== 0).map((l) => l.code);
      return `changed ${changed.join(", ")}`;
    }
    case "price_change":
      return `direct cost ${aed((r as PriceResult).direct_cost_aed)}`;
    case "compare_contractor_claim": {
      const c = r as ClaimComparisonResult;
      return `claimed ${aed(c.claimed_total_aed)}, assessed ${aed(c.assessed_direct_cost_aed)}`;
    }
    case "added_duration": {
      const a = r as AddedDurationResult;
      return a.activities.map((x) => `${x.activity_id} +${x.added_days}`).join(", ");
    }
    case "run_cpm": {
      const c = r as CpmResult;
      return `completion day ${c.completion_working_day} (${formatDate(c.completion_date)})`;
    }
    case "evaluate_option": {
      const o = r as OptionResult;
      return `${o.option_id}: delay ${workingDays(o.delay_working_days)}, total ${aed(o.total_cost_aed)}`;
    }
    case "search_options": {
      const s = r as SearchOptionsResult;
      return `Pareto set ${s.pareto_option_ids.join(", ")}`;
    }
    case "check_buffer": {
      const b = r as BufferResult;
      return `${b.option_id}: ${b.time_buffer_remaining_days} wd buffer left, contingency left ${aed(b.contingency_remaining_aed)}`;
    }
    case "search_contract":
      return `clauses ${(r as { hits: ClauseResult[] }).hits.map((h) => h.clause).join(", ")}`;
    case "get_clause": {
      const c = r as ClauseResult;
      return `${c.clause} ${c.title}`;
    }
    case "search_boq":
      return `items ${((r as { hits?: { code: string }[] }).hits ?? []).map((h) => h.code).join(", ")}`;
    case "get_boq_item":
      return (r as { code?: string }).code ?? "";
    case "propose_action":
      return `${(r as { action_id?: string }).action_id ?? ""} waiting for approval`;
    default:
      return "";
  }
}

/** Short argument text for tool calls whose arguments are worth seeing. */
export function toolArgs(call: ToolCallView): string {
  const a = call.args;
  switch (call.tool) {
    case "search_contract":
    case "search_boq":
      return typeof a.query === "string" ? `"${a.query}"` : "";
    case "get_clause":
      return String(a.clause_id ?? "");
    case "get_boq_item":
      return String(a.code ?? "");
    case "evaluate_option":
      return Array.isArray(a.extra_crews_on) ? `crews on ${a.extra_crews_on.join(", ") || "none"}` : "";
    case "check_buffer":
      return String(a.option_id ?? "");
    case "run_cpm":
      return a.include_change_durations === false ? "baseline" : "with the change";
    case "propose_action":
      return String(a.type ?? "");
    default:
      return "";
  }
}
