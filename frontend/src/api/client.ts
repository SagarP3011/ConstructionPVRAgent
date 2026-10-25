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

export const api = {
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
