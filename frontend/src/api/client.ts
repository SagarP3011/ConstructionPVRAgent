/** REST and Server-Sent Events client for the backend (SPEC 11.1). */

import type { Mode, RunEvent } from "./events";

export interface ParameterSpec {
  name: string;
  label: string;
  default: number;
  min: number;
  max: number;
  step: number;
}

export interface ChangeType {
  id: string;
  title: string;
  element: string;
  parameters: ParameterSpec[];
  fixed: Record<string, number>;
  has_contractor_claim_at_default: boolean;
  default_instruction: string;
  modes: Mode[];
}

export interface StoredRun {
  id: string;
  source: "fixture" | "run";
  run_id: string;
  kind: string;
  state: string;
  live: boolean;
  change_type: string | null;
  parameters: Record<string, number> | null;
  mode: Mode | null;
  overrides: RunOverrides | null;
  started_at: string | null;
  ended_at: string | null;
  event_count: number;
  chosen_option: string | null;
  /** A decision replay: the recorded run it was brought back from. */
  replay_of: string | null;
}

/** What-if limits for a run; null keeps the project's value. */
export interface RunOverrides {
  cost_contingency_remaining_aed: number | null;
  time_buffer_working_days: number | null;
}

export interface StartRunBody {
  change_type: string;
  parameters: Record<string, number>;
  mode: Mode;
  overrides?: RunOverrides;
}

export interface ApproveBody {
  option_id: string;
  action_ids: string[];
  approver_name: string;
  approver_role: string;
}

export interface RejectBody {
  approver_name: string;
  approver_role: string;
  reason: string;
}

export interface Clause {
  clause: string;
  title: string;
  text: string;
}

export interface ProjectInfo {
  name: string;
  contract_completion_working_day: number;
  contract_completion_date: string;
  employer_commitment_working_day: number;
  employer_commitment_date: string;
  time_buffer_working_days: number;
  cost_contingency_remaining_aed: number;
}

/** An error from the backend, with its `detail` message when it sent one. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
  });
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail)) detail = body.detail.map((d: { msg?: string }) => d.msg ?? "").join("; ");
    } catch {
      // keep the HTTP status as the message
    }
    throw new ApiError(detail, response.status);
  }
  return (await response.json()) as T;
}

/** The Intake agent's reading of a typed request (POST /api/interpret). */
export interface Interpretation {
  status: "interpreted" | "declined";
  change_type: string | null;
  title: string | null;
  parameters: Record<string, number>;
  mode: Mode | null;
  instruction_text: string | null;
  reading: string;
  reason: string;
}

// --- Rates and assumptions (read-only, GET /api/assumptions) ---------------------------------------------

export interface WorkRate {
  boq_code: string;
  description: string;
  unit: string;
  rate_aed: number;
  activity_id: string;
  activity_name: string;
  baseline_duration: number;
  output_per_crew_day: number;
}

export interface CrewAssumption {
  activity_id: string;
  activity_name: string;
  crew_name: string;
  trades: { trade: string; count: number }[];
  people: number;
  hours_per_day: number;
  equipment: string[];
  work_items: { boq_code: string; unit: string; output_per_crew_day: number; labour_hours_per_unit: number }[];
}

export interface ScheduleActivity {
  activity_id: string;
  name: string;
  duration: number;
  early_start: number;
  early_finish: number;
  total_float: number;
  critical: boolean;
}

export interface QuantityRule {
  change_type: string;
  title: string;
  element: string;
  parameters: ParameterSpec[];
  fixed: Record<string, number>;
  geometry: Record<string, unknown>;
  lines: { code: string; description: string; unit: string; basis: string }[];
  unaffected: { code: string; description: string; reason: string }[];
  requires_review: { code: string; description: string; reason: string; needs_new_rate: boolean }[];
}

export interface Assumptions {
  work_rates: { units: string; rule: string; items: WorkRate[]; source: string };
  crews: { status: string; note: string; items: CrewAssumption[]; source: string };
  cost: {
    rate_source: string;
    direct_cost_rule: string;
    time_related_cost_per_working_day_aed: number;
    additional_crew: {
      mobilisation_aed_per_crew_per_activity: number;
      day_rate_aed: number;
      max_additional_crews_per_activity: number;
      rule: string;
      eligible_activities_by_change_type: Record<string, string[]>;
    };
    cost_contingency_remaining_aed: number;
    total_cost_rule: string;
    clauses: Clause[];
    source: string;
  };
  time: {
    calendar: { start_date: string; working_days: string[]; non_working_days: string[]; holidays: string[] };
    data_date: string;
    data_date_working_day: number;
    contract_completion_working_day: number;
    contract_completion_date: string;
    employer_commitment_working_day: number;
    employer_commitment_date: string;
    time_buffer_working_days: number;
    added_duration_rule: string;
    additional_crew_rule: string;
    delay_rule: string;
    buffer_rule: string;
    pareto_rule: string;
    baseline_completion_working_day: number;
    baseline_completion_date: string;
    baseline_critical_path: string[];
    activities: ScheduleActivity[];
    clauses: Clause[];
    source: string;
  };
  quantity_rules: QuantityRule[];
  quantity_rules_source: string;
}

export interface WorkedExample {
  change_type: string;
  parameters: Record<string, number>;
  quantities: { code: string; description: string; unit: string; old: number | null; new: number | null; delta: number; basis: string }[];
  requires_review: { code: string; description: string; reason: string; needs_new_rate: boolean }[];
  cost: {
    rate_source: string;
    direct_cost_aed: number;
    lines: { code: string; description: string; unit: string; delta: number; rate_aed: number; amount_aed: number }[];
    unpriced_items: { code: string; description: string; reason: string }[];
  };
  durations: {
    activity_id: string;
    name: string;
    baseline_duration: number;
    added_days: number;
    new_duration: number;
    baseline_total_float: number;
    items: { code: string; delta: number; productivity_per_day: number; crew_days: number }[];
  }[];
  contract_completion_working_day: number;
  baseline_completion_working_day: number;
  no_extra_crews: {
    option_id: string;
    completion_working_day: number;
    completion_date: string;
    delay_working_days: number;
    direct_cost_aed: number;
    acceleration_cost_aed: number;
    time_related_cost_aed: number;
    total_cost_aed: number;
    time_buffer_remaining_days: number;
    contingency_remaining_aed: number;
  };
  one_extra_crew: {
    option_id: string;
    activity_id: string;
    duration_before: number;
    duration_after: number;
    crew_cost_aed: number;
    delay_working_days: number;
    total_cost_aed: number;
  }[];
  time_related_cost_per_working_day_aed: number;
  source: string;
}

export const api = {
  assumptions: () => request<Assumptions>("/api/assumptions"),
  workedExample: (changeType: string, parameters: Record<string, number>) => {
    const query = new URLSearchParams(Object.entries(parameters).map(([k, v]) => [k, String(v)])).toString();
    return request<WorkedExample>(`/api/assumptions/example/${encodeURIComponent(changeType)}${query ? `?${query}` : ""}`);
  },
  interpret: (text: string) =>
    request<Interpretation>("/api/interpret", { method: "POST", body: JSON.stringify({ text }) }),
  changeTypes: () => request<ChangeType[]>("/api/change-types"),
  project: () => request<ProjectInfo>("/api/data/project"),
  contract: () => request<{ contract_ref: string; clauses: Clause[] }>("/api/data/contract"),
  listRuns: () => request<StoredRun[]>("/api/runs"),
  startRun: (body: StartRunBody) =>
    request<{ run_id: string; events_url: string }>("/api/runs", { method: "POST", body: JSON.stringify(body) }),
  /** Bring a recorded run back to its decision as a new run; replay that run and decide it. */
  replayToDecision: (traceId: string) =>
    request<{ run_id: string; events_url: string }>(`/api/replay/${encodeURIComponent(traceId)}/decision`, {
      method: "POST",
    }),
  approve: (runId: string, body: ApproveBody) =>
    request<{ status: string; executed_actions: unknown[] }>(`/api/runs/${encodeURIComponent(runId)}/approve`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  reject: (runId: string, body: RejectBody) =>
    request<{ status: string }>(`/api/runs/${encodeURIComponent(runId)}/reject`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  outputText: async (runId: string, file: string): Promise<string> => {
    const response = await fetch(outputUrl(runId, file));
    if (!response.ok) throw new ApiError(`Could not load ${file}`, response.status);
    return response.text();
  },
};

export function outputUrl(runId: string, file: string): string {
  return `/api/runs/${encodeURIComponent(runId)}/outputs/${encodeURIComponent(file)}`;
}

// --- event streams ---------------------------------------------------------------------------------

export type StreamSource =
  | { kind: "live"; runId: string }
  | { kind: "replay"; traceId: string; speed: number; /** pauses for a person's decision */ decide?: boolean };

export function streamUrl(source: StreamSource, after: string | null): string {
  const query = new URLSearchParams();
  if (source.kind === "replay") query.set("speed", String(source.speed));
  if (after) query.set("after", after);
  const qs = query.toString();
  const base =
    source.kind === "live"
      ? `/api/runs/${encodeURIComponent(source.runId)}/events`
      : `/api/replay/${encodeURIComponent(source.traceId)}`;
  return qs ? `${base}?${qs}` : base;
}

export interface StreamHandlers {
  onEvent: (event: RunEvent) => void;
  onEnd: (reason: string) => void;
  onError: (message: string) => void;
}

/**
 * Open an SSE stream. Returns a function that closes it. The server sends a named `end` event when
 * there is nothing more; the stream is closed then, so the browser does not reconnect and repeat it.
 */
export function openStream(source: StreamSource, after: string | null, handlers: StreamHandlers): () => void {
  const es = new EventSource(streamUrl(source, after));
  let closed = false;
  const close = () => {
    closed = true;
    es.close();
  };
  es.onmessage = (msg: MessageEvent<string>) => {
    if (!closed) handlers.onEvent(JSON.parse(msg.data) as RunEvent);
  };
  es.addEventListener("end", (msg) => {
    const reason = (JSON.parse((msg as MessageEvent<string>).data) as { reason: string }).reason;
    close();
    handlers.onEnd(reason);
  });
  es.onerror = () => {
    // EventSource reconnects on its own (sending Last-Event-ID); report only a closed connection.
    if (!closed && es.readyState === EventSource.CLOSED) handlers.onError("The connection to the backend was lost.");
  };
  return close;
}
