/**
 * Typed events from the backend (SPEC 11.2). Every event is `{event_id, run_id, type, ts, payload}`.
 * Live runs and replays stream the same events, and the UI renders from them only.
 */

export type AgentId = "moderator" | "intake" | "contract" | "cost" | "time" | "commercial" | "verifier";
export type Mode = "contractor_pvr" | "internal_what_if";
export type Intent = "ASSESS" | "PROPOSE" | "CHALLENGE" | "AGREE" | "ASK" | "ANSWER" | "VERIFY" | "SUMMARISE";

export interface RunContext {
  change_type: string;
  parameters: Record<string, number>;
  mode: Mode;
  overrides: { cost_contingency_remaining_aed: number | null; time_buffer_working_days: number | null };
}

export interface Claim {
  label: string;
  value: number | string;
  unit: string;
  fact_id: string;
}

export interface AgentMessage {
  message_id: string;
  run_id: string;
  stage: string;
  round: number;
  from: AgentId;
  to: AgentId | "all";
  intent: Intent;
  content: string;
  claims: Claim[];
  stance: string | null;
  proposals: string[];
  verification: { status: "pass" | "fail" | "pending"; issues: string[] };
  corrects: string | null;
  superseded_by: string | null;
  timestamp: string;
}

export interface Fact {
  fact_id: string;
  tool_call_id: string;
  tool: string;
  path: string;
  value: number | string;
  unit: string;
}

/** An executed or pending action proposed by an agent. */
export interface Action {
  action_id: string;
  type: "create_task" | "draft_pvr_form" | "draft_verification_report" | "notify" | string;
  payload: Record<string, unknown>;
  reason: string;
  proposed_by: AgentId | string;
  status: "pending" | "approved" | "not_approved" | "executed" | string;
}

// --- tool results used by the panels ----------------------------------------------------------------

export interface ChangeParameter {
  name: string;
  label: string;
  value: number;
  default: number;
  min: number;
  max: number;
  step: number;
}

export interface ClaimedLine {
  description: string;
  unit: string;
  quantity: number;
  rate_aed: number;
}

export interface ChangeRequestResult {
  id: string;
  change_type: string;
  title: string;
  element: string;
  mode: Mode;
  parameters: ChangeParameter[];
  fixed: Record<string, number>;
  instruction_text: string;
  variation_instruction: { ref: string; date: string; issued_by: string; text: string } | null;
  contractor_pvr: {
    ref: string;
    date: string;
    contractor: string;
    subject: string;
    text: string;
    claimed_lines: ClaimedLine[];
    claimed_preliminaries_percent: number;
    claimed_total_aed: number;
    claimed_extension_working_days: number;
  } | null;
}

export interface DrawingComparisonResult {
  change_type: string;
  element: string;
  drawing: string;
  from_revision: string;
  to_revision: string | null;
  to_revision_note: string;
  changes: { parameter: string; old: number | null; new: number | null; unit: string; note: string }[];
  geometry: Record<string, unknown>;
}

export interface NoticeResult {
  event_date: string;
  notice_date: string;
  calendar_days: number;
  limit_days: number;
  within_limit: boolean;
  clause: string;
}

export interface QuantityLine {
  code: string;
  description: string;
  unit: string;
  old: number | null;
  new: number | null;
  delta: number;
  basis: string;
}

export interface ReviewItem {
  code: string;
  description: string;
  reason: string;
  needs_new_rate?: boolean;
}

export interface QuantifyResult {
  change_type: string;
  lines: QuantityLine[];
  unaffected: ReviewItem[];
  requires_review: ReviewItem[];
}

export interface CostLine {
  code: string;
  description: string;
  unit: string;
  delta: number;
  rate_aed: number;
  amount_aed: number;
  rate_source: string;
}

export interface PriceResult {
  change_type: string;
  lines: CostLine[];
  rate_source: string;
  direct_cost_aed: number;
  unpriced_items: (ReviewItem & { amount_aed: number })[];
}

export interface ClaimComparisonLine {
  claimed_description: string;
  matched_code: string | null;
  boq_description: string | null;
  unit: string;
  claimed_quantity: number;
  assessed_quantity: number | null;
  claimed_rate_aed: number;
  boq_rate_aed: number | null;
  claimed_amount_aed: number;
  assessed_amount_aed: number | null;
  amount_difference_aed: number | null;
  clause: string;
}

export interface ClaimComparisonResult {
  pvr_ref: string;
  instruction_ref: string;
  lines: ClaimComparisonLine[];
  claimed_subtotal_aed: number;
  claimed_preliminaries_percent: number;
  claimed_preliminaries_aed: number;
  allowed_preliminaries_aed: number;
  claimed_total_aed: number;
  assessed_direct_cost_aed: number;
  difference_direct_aed: number;
  claimed_extension_days: number;
  assessed_extension_days_without_acceleration: number;
  adjustments: {
    item: string;
    claimed: number;
    assessed: number;
    difference: number;
    unit: string;
    clause: string;
    reason: string;
  }[];
}

export interface AddedDurationResult {
  change_type: string;
  rule: string;
  activities: {
    activity_id: string;
    name: string;
    baseline_duration: number;
    added_days: number;
    new_duration: number;
  }[];
  total_added_days: number;
}

export interface CpmActivity {
  activity_id: string;
  name: string;
  duration: number;
  ES: number;
  EF: number;
  LS: number;
  LF: number;
  TF: number;
  critical: boolean;
  start_date: string;
  finish_date: string;
}

export interface CpmResult {
  completion_working_day: number;
  completion_date: string;
  critical_path: string[];
  activities: Record<string, CpmActivity>;
}

export interface OptionResult {
  option_id: string;
  extra_crews_on: string[];
  accelerated: { activity_id: string; duration_before: number; duration_after: number; crew_cost_aed: number }[];
  completion_working_day: number;
  completion_date: string;
  delay_working_days: number;
  direct_cost_aed: number;
  acceleration_cost_aed: number;
  time_related_cost_aed: number;
  total_cost_aed: number;
  time_buffer_remaining_days: number;
  contingency_remaining_aed: number;
  critical_path: string[];
}

export interface SearchOptionsResult {
  change_type: string;
  eligible_activities: string[];
  options: OptionResult[];
  pareto_option_ids: string[];
  pareto_rule: string;
}

export interface BufferResult {
  option_id: string;
  delay_working_days: number;
  total_cost_aed: number;
  time_buffer_days: number;
  contingency_aed: number;
  time_buffer_remaining_days: number;
  contingency_remaining_aed: number;
  within_time_buffer: boolean;
  within_contingency: boolean;
  budget_uplift_needed_aed: number;
  exceeds_employer_commitment: boolean;
}

export interface ClauseResult {
  clause: string;
  title: string;
  text: string;
}

export type FinalOption = OptionResult & { supported_by: AgentId[] };

// --- events -----------------------------------------------------------------------------------------

export interface EventPayloads {
  "run.started": { context: RunContext; kind: "full" | "single_agent"; model?: string; model_light?: string };
  "stage.started": { stage: string };
  "stage.completed": { stage: string; rounds?: number; stop_reason?: string };
  "agent.active": { agent: AgentId; stage: string; round: number; model: string; tools: string[]; answer_turn: boolean };
  "agent.idle": { agent: AgentId; status: "posted" | "failed"; steps: number; forced: boolean; error: string; message_id: string | null };
  "llm.call": {
    agent: AgentId;
    model: string;
    step: number;
    prompt_tokens: number;
    completion_tokens: number;
    latency_ms: number;
    tool_calls: string[];
  };
  "tool.called": { tool_call_id: string; agent: AgentId | "orchestrator"; tool: string; args: Record<string, unknown> };
  "tool.result": {
    tool_call_id: string;
    agent: AgentId | "orchestrator";
    tool: string;
    ok: boolean;
    result: unknown;
    error: string;
    fact_ids: string[];
  };
  "fact.registered": Fact;
  "ask.sent": { message_id: string; from: AgentId; to: AgentId; question: string };
  "ask.answered": { message_id: string; from: AgentId; to: AgentId; answer_message_id: string | null };
  "message.posted": AgentMessage;
  "verification.result": {
    message_id: string;
    agent: AgentId;
    status: "pass" | "fail";
    issues: string[];
    unresolved: boolean;
    claims_checked: number;
  };
  "message.corrected": { original_message_id: string; corrected_message_id: string; agent: AgentId };
  "stance.changed": { agent: AgentId; from: string | null; to: string; when: string; message_id: string };
  "option.evaluated": { option_id: string; agent: AgentId; tool_call_id: string; delay_working_days: number; total_cost_aed: number };
  "options.final": {
    source: "moderator" | "pareto_fallback";
    options: FinalOption[];
    stances: Partial<Record<AgentId, string | null>>;
    debate_rounds: number;
    debate_stop_reason: string;
  };
  "action.proposed": Action;
  "approval.requested": { options: string[]; pending_actions: Action[]; stances: Partial<Record<AgentId, string | null>> };
  "approval.granted": {
    status: "approved";
    option_id: string;
    approved_action_ids: string[];
    approver_name: string;
    approver_role: string;
    timestamp: string;
  };
  "approval.rejected": { status: "rejected"; approver_name: string; approver_role: string; reason: string; timestamp: string };
  "action.executed": { action_id: string; type: string; files: string[]; executed_at: string };
  "run.completed": { status: "approved" | "rejected" | string; option_id?: string; executed_actions?: string[] };
  "run.error": { error: string; agent?: string; fatal?: boolean; stage?: string };
}

export type EventType = keyof EventPayloads;

export interface RunEventOf<T extends EventType> {
  event_id: string;
  run_id: string;
  type: T;
  ts: string;
  payload: EventPayloads[T];
}

/** Any event, discriminated by `type`. */
export type RunEvent = { [T in EventType]: RunEventOf<T> }[EventType];
