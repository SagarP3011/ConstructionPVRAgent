/**
 * Event-driven run state. `reduceEvents` folds backend events into what the panels show, the same way
 * for live runs and replays. The UI never computes business numbers: every value here was carried by
 * an event.
 */

import type {
  Action,
  AddedDurationResult,
  AgentId,
  AgentMessage,
  BufferResult,
  ChangeRequestResult,
  ClaimComparisonResult,
  ClauseResult,
  CpmResult,
  DrawingComparisonResult,
  EventPayloads,
  Fact,
  FinalOption,
  NoticeResult,
  OptionResult,
  PriceResult,
  QuantifyResult,
  RunContext,
  RunEvent,
  SearchOptionsResult,
} from "../api/events";
import { AGENT_IDS, isAgentId } from "./agents";

export type RunStatus = "idle" | "running" | "awaiting_approval" | "completed" | "rejected" | "failed";

export interface ToolCallView {
  id: string;
  agent: AgentId | "orchestrator";
  tool: string;
  args: Record<string, unknown>;
  ok: boolean | null; // null while running
  error: string;
  result: unknown;
  factIds: string[];
  stage: string | null;
  seq: number;
}

export interface MessageView extends AgentMessage {
  seq: number;
  unresolved: boolean;
}

export type TimelineItem =
  | { kind: "stage"; stage: string; seq: number }
  | { kind: "message"; id: string; seq: number }
  | { kind: "tool"; id: string; seq: number };

/** A message or question travelling between agents, drawn on the Agent Room graph. */
export interface Flight {
  seq: number;
  from: AgentId;
  to: AgentId | "all";
  kind: "message" | "ask" | "answer";
}

export interface StanceChange {
  when: string;
  from: string | null;
  to: string;
  messageId: string;
}

export interface AgentView {
  id: AgentId;
  active: boolean;
  stance: string | null;
  stanceHistory: StanceChange[];
  lastTool: { tool: string; seq: number } | null;
  toolCalls: number;
  messages: number;
}

export interface Results {
  changeRequest: ChangeRequestResult | null;
  drawing: DrawingComparisonResult | null;
  notice: NoticeResult | null;
  quantities: QuantifyResult | null;
  price: PriceResult | null;
  claim: ClaimComparisonResult | null;
  addedDuration: AddedDurationResult | null;
  baselineCpm: CpmResult | null;
  impactedCpm: CpmResult | null;
  searchOptions: SearchOptionsResult | null;
  buffers: Record<string, BufferResult>;
  clauses: Record<string, ClauseResult>;
}

export interface RunState {
  runId: string | null;
  context: RunContext | null;
  model: string | null;
  status: RunStatus;
  stage: string | null;
  stagesDone: string[];
  agents: Record<AgentId, AgentView>;
  messages: Record<string, MessageView>;
  tools: Record<string, ToolCallView>;
  timeline: TimelineItem[];
  facts: Record<string, Fact>;
  results: Results;
  /** Every option evaluated in this run, by id (from search_options and evaluate_option). */
  options: Record<string, OptionResult>;
  flights: Flight[];
  finalOptions: FinalOption[] | null;
  finalStances: Partial<Record<AgentId, string | null>>;
  debate: { rounds: number; stopReason: string } | null;
  actions: Record<string, Action>;
  actionOrder: string[];
  approvalRequested: boolean;
  decision: EventPayloads["approval.granted"] | EventPayloads["approval.rejected"] | null;
  executed: EventPayloads["action.executed"][];
  errors: EventPayloads["run.error"][];
  llm: { calls: number; promptTokens: number; completionTokens: number };
  eventCount: number;
  lastEventId: string | null;
  seq: number;
}

const MAX_FLIGHTS = 24;
/** Tool calls the timeline does not show as rows (they appear as messages or are internal). */
const HIDDEN_TOOLS = new Set(["post_message", "ask_agent", "read_blackboard"]);

function emptyAgents(): Record<AgentId, AgentView> {
  const agents = {} as Record<AgentId, AgentView>;
  for (const id of AGENT_IDS) {
    agents[id] = { id, active: false, stance: null, stanceHistory: [], lastTool: null, toolCalls: 0, messages: 0 };
  }
  return agents;
}

export function initialRunState(): RunState {
  return {
    runId: null,
    context: null,
    model: null,
    status: "idle",
    stage: null,
    stagesDone: [],
    agents: emptyAgents(),
    messages: {},
    tools: {},
    timeline: [],
    facts: {},
    results: {
      changeRequest: null,
      drawing: null,
      notice: null,
      quantities: null,
      price: null,
      claim: null,
      addedDuration: null,
      baselineCpm: null,
      impactedCpm: null,
      searchOptions: null,
      buffers: {},
      clauses: {},
    },
    options: {},
    flights: [],
    finalOptions: null,
    finalStances: {},
    debate: null,
    actions: {},
    actionOrder: [],
    approvalRequested: false,
    decision: null,
    executed: [],
    errors: [],
    llm: { calls: 0, promptTokens: 0, completionTokens: 0 },
    eventCount: 0,
    lastEventId: null,
    seq: 0,
  };
}

/** Shallow copies of the containers this batch writes to, so the old state stays intact. Containers the
 * batch does not touch keep their identity (the fact map alone holds a few thousand entries). */
function cloneForBatch(s: RunState, events: RunEvent[]): RunState {
  const types = new Set(events.map((e) => e.type));
  const any = (...names: RunEvent["type"][]) => names.some((n) => types.has(n));
  const toolResults = types.has("tool.result");
  const messages = any("message.posted", "verification.result", "message.corrected");
  const actions = any("action.proposed", "approval.requested", "approval.granted", "action.executed");
  return {
    ...s,
    stagesDone: types.has("stage.completed") ? [...s.stagesDone] : s.stagesDone,
    agents: { ...s.agents },
    messages: messages ? { ...s.messages } : s.messages,
    tools: any("tool.called", "tool.result") ? { ...s.tools } : s.tools,
    timeline: any("stage.started", "tool.called", "message.posted") ? [...s.timeline] : s.timeline,
    facts: types.has("fact.registered") ? { ...s.facts } : s.facts,
    results: toolResults ? { ...s.results, buffers: { ...s.results.buffers }, clauses: { ...s.results.clauses } } : s.results,
    options: toolResults ? { ...s.options } : s.options,
    flights: any("ask.sent", "message.posted") ? [...s.flights] : s.flights,
    finalStances: types.has("options.final") ? { ...s.finalStances } : s.finalStances,
    actions: actions ? { ...s.actions } : s.actions,
    actionOrder: actions ? [...s.actionOrder] : s.actionOrder,
    executed: types.has("action.executed") ? [...s.executed] : s.executed,
    errors: types.has("run.error") ? [...s.errors] : s.errors,
    llm: types.has("llm.call") ? { ...s.llm } : s.llm,
  };
}

/** Agents changed in the current batch get their own copy; the others keep their identity, so
 * components showing an unchanged agent can skip re-rendering. */
let touched = new Set<AgentId>();

function agentFor(s: RunState, id: AgentId): AgentView {
  if (!touched.has(id)) {
    s.agents[id] = { ...s.agents[id], stanceHistory: [...s.agents[id].stanceHistory] };
    touched.add(id);
  }
  return s.agents[id];
}

function addFlight(s: RunState, flight: Omit<Flight, "seq">): void {
  s.flights.push({ ...flight, seq: s.seq });
  if (s.flights.length > MAX_FLIGHTS) s.flights.splice(0, s.flights.length - MAX_FLIGHTS);
}

function isBaselineCpm(call: ToolCallView): boolean {
  return call.agent === "orchestrator" || call.args.include_change_durations === false;
}

function hasOverrides(call: ToolCallView): boolean {
  const overrides = call.args.duration_overrides;
  return typeof overrides === "object" && overrides !== null && Object.keys(overrides).length > 0;
}

/** Keep the results the panels need, by tool. Only successful calls by agents (and the orchestrator's
 * baseline run) count; the orchestrator's blackboard reads are agent context, not results. */
function recordResult(s: RunState, call: ToolCallView): void {
  const r = s.results;
  const result = call.result;
  switch (call.tool) {
    case "get_change_request":
      r.changeRequest = result as ChangeRequestResult;
      break;
    case "compare_drawing_revisions":
      r.drawing = result as DrawingComparisonResult;
      break;
    case "check_notice":
      r.notice = result as NoticeResult;
      break;
    case "quantify_change":
      r.quantities = result as QuantifyResult;
      break;
    case "price_change":
      r.price = result as PriceResult;
      break;
    case "compare_contractor_claim":
      r.claim = result as ClaimComparisonResult;
      break;
    case "added_duration":
      r.addedDuration = result as AddedDurationResult;
      break;
    case "run_cpm":
      if (hasOverrides(call)) break;
      if (isBaselineCpm(call)) r.baselineCpm = result as CpmResult;
      else r.impactedCpm = result as CpmResult;
      break;
    case "search_options": {
      const found = result as SearchOptionsResult;
      r.searchOptions = found;
      for (const option of found.options) s.options[option.option_id] = option;
      break;
    }
    case "evaluate_option": {
      const option = result as OptionResult;
      s.options[option.option_id] = option;
      break;
    }
    case "check_buffer": {
      const buffer = result as BufferResult;
      r.buffers[buffer.option_id] = buffer;
      break;
    }
    case "get_clause": {
      const clause = result as ClauseResult;
      r.clauses[clause.clause] = clause;
      break;
    }
    case "search_contract":
      for (const hit of (result as { hits: ClauseResult[] }).hits) r.clauses[hit.clause] = hit;
      break;
    default:
      break;
  }
}

function apply(s: RunState, event: RunEvent): void {
  s.seq += 1;
  s.eventCount += 1;
  s.lastEventId = event.event_id;
  s.runId = event.run_id;

  switch (event.type) {
    case "run.started":
      s.context = event.payload.context;
      s.model = event.payload.model ?? null;
      s.status = "running";
      break;
    case "stage.started":
      s.stage = event.payload.stage;
      s.timeline.push({ kind: "stage", stage: event.payload.stage, seq: s.seq });
      break;
    case "stage.completed":
      if (!s.stagesDone.includes(event.payload.stage)) s.stagesDone.push(event.payload.stage);
      if (event.payload.stage === "debate" && event.payload.rounds !== undefined) {
        s.debate = { rounds: event.payload.rounds, stopReason: event.payload.stop_reason ?? "" };
      }
      break;
    case "agent.active":
      if (isAgentId(event.payload.agent)) agentFor(s, event.payload.agent).active = true;
      break;
    case "agent.idle":
      if (isAgentId(event.payload.agent)) agentFor(s, event.payload.agent).active = false;
      break;
    case "llm.call":
      s.llm.calls += 1;
      s.llm.promptTokens += event.payload.prompt_tokens;
      s.llm.completionTokens += event.payload.completion_tokens;
      break;
    case "tool.called": {
      const p = event.payload;
      s.tools[p.tool_call_id] = {
        id: p.tool_call_id,
        agent: p.agent,
        tool: p.tool,
        args: p.args,
        ok: null,
        error: "",
        result: null,
        factIds: [],
        stage: s.stage,
        seq: s.seq,
      };
      if (isAgentId(p.agent)) {
        const agent = agentFor(s, p.agent);
        agent.toolCalls += 1;
        if (!HIDDEN_TOOLS.has(p.tool)) {
          agent.lastTool = { tool: p.tool, seq: s.seq };
          s.timeline.push({ kind: "tool", id: p.tool_call_id, seq: s.seq });
        }
      }
      break;
    }
    case "tool.result": {
      const p = event.payload;
      const previous = s.tools[p.tool_call_id];
      if (!previous) break;
      const call: ToolCallView = { ...previous, ok: p.ok, error: p.error, result: p.result, factIds: p.fact_ids };
      s.tools[p.tool_call_id] = call;
      if (p.ok && (isAgentId(p.agent) || (p.agent === "orchestrator" && p.tool === "run_cpm"))) {
        recordResult(s, call);
      }
      break;
    }
    case "fact.registered":
      s.facts[event.payload.fact_id] = event.payload;
      break;
    case "ask.sent":
      addFlight(s, { from: event.payload.from, to: event.payload.to, kind: "ask" });
      break;
    case "message.posted": {
      const m = event.payload;
      s.messages[m.message_id] = { ...m, seq: s.seq, unresolved: false };
      s.timeline.push({ kind: "message", id: m.message_id, seq: s.seq });
      if (isAgentId(m.from)) agentFor(s, m.from).messages += 1;
      // Questions fly with ask.sent; everything else flies when posted.
      if (m.intent !== "ASK" && isAgentId(m.from)) {
        addFlight(s, { from: m.from, to: m.to, kind: m.intent === "ANSWER" ? "answer" : "message" });
      }
      break;
    }
    case "verification.result": {
      const p = event.payload;
      const m = s.messages[p.message_id];
      if (m) {
        s.messages[p.message_id] = {
          ...m,
          verification: { status: p.status, issues: p.issues },
          unresolved: p.unresolved,
        };
      }
      break;
    }
    case "message.corrected": {
      const p = event.payload;
      const original = s.messages[p.original_message_id];
      const corrected = s.messages[p.corrected_message_id];
      if (original) s.messages[p.original_message_id] = { ...original, superseded_by: p.corrected_message_id };
      if (corrected) s.messages[p.corrected_message_id] = { ...corrected, corrects: p.original_message_id };
      break;
    }
    case "stance.changed": {
      const p = event.payload;
      if (isAgentId(p.agent)) {
        const agent = agentFor(s, p.agent);
        agent.stance = p.to;
        agent.stanceHistory.push({ when: p.when, from: p.from, to: p.to, messageId: p.message_id });
      }
      break;
    }
    case "option.evaluated":
      break; // the full option arrives with the evaluate_option tool result
    case "options.final":
      s.finalOptions = event.payload.options;
      s.finalStances = event.payload.stances;
      for (const id of AGENT_IDS) {
        const stance = event.payload.stances[id];
        if (stance && s.agents[id].stance !== stance) agentFor(s, id).stance = stance;
      }
      s.debate = { rounds: event.payload.debate_rounds, stopReason: event.payload.debate_stop_reason };
      break;
    case "action.proposed":
      if (!(event.payload.action_id in s.actions)) s.actionOrder.push(event.payload.action_id);
      s.actions[event.payload.action_id] = event.payload;
      break;
    case "approval.requested":
      s.approvalRequested = true;
      s.status = "awaiting_approval";
      for (const action of event.payload.pending_actions) {
        if (!(action.action_id in s.actions)) s.actionOrder.push(action.action_id);
        s.actions[action.action_id] = action;
      }
      break;
    case "approval.granted":
      s.decision = event.payload;
      for (const id of s.actionOrder) {
        const action = s.actions[id];
        if (action) {
          const approved = event.payload.approved_action_ids.includes(id);
          s.actions[id] = { ...action, status: approved ? "approved" : "not_approved" };
        }
      }
      break;
    case "approval.rejected":
      s.decision = event.payload;
      break;
    case "action.executed": {
      s.executed.push(event.payload);
      const action = s.actions[event.payload.action_id];
      if (action) s.actions[event.payload.action_id] = { ...action, status: "executed" };
      break;
    }
    case "run.completed":
      s.status = event.payload.status === "rejected" ? "rejected" : "completed";
      for (const id of AGENT_IDS) if (s.agents[id].active) agentFor(s, id).active = false;
      break;
    case "run.error":
      s.errors.push(event.payload);
      if (event.payload.fatal) {
        s.status = "failed";
        for (const id of AGENT_IDS) if (s.agents[id].active) agentFor(s, id).active = false;
      }
      break;
  }
}

/** Apply a batch of events. Returns a new state; the given state is not changed. */
export function reduceEvents(state: RunState, events: RunEvent[]): RunState {
  if (events.length === 0) return state;
  const next = cloneForBatch(state, events);
  touched = new Set();
  for (const event of events) apply(next, event);
  touched = new Set();
  return next;
}

// --- selectors ------------------------------------------------------------------------------------

/** Timeline items to show: a superseded message is replaced by its correction at its own position. */
export function visibleTimeline(state: RunState, agentFilter: AgentId | null): TimelineItem[] {
  const corrected = new Set(
    Object.values(state.messages)
      .filter((m) => m.corrects)
      .map((m) => m.message_id),
  );
  return state.timeline.filter((item) => {
    if (item.kind === "stage") return agentFilter === null;
    if (item.kind === "tool") return agentFilter === null || state.tools[item.id]?.agent === agentFilter;
    const m = state.messages[item.id];
    if (!m || corrected.has(m.message_id)) return false;
    if (agentFilter === null) return true;
    const shown = m.superseded_by ? state.messages[m.superseded_by] ?? m : m;
    return shown.from === agentFilter || shown.to === agentFilter;
  });
}

/** Clause ids cited in messages ("clause 13.3", "clauses 8.4 and 8.5"), in order of first mention. */
export function citedClauses(state: RunState): string[] {
  const found: string[] = [];
  const pattern = /\bclauses?\s+(\d+(?:\.\d+)*(?:\s*(?:,|and|or|&|\/)\s*\d+(?:\.\d+)*)*)/gi;
  for (const item of state.timeline) {
    if (item.kind !== "message") continue;
    const m = state.messages[item.id];
    if (!m || m.superseded_by) continue;
    for (const match of m.content.matchAll(pattern)) {
      for (const id of (match[1] ?? "").match(/\d+(?:\.\d+)*/g) ?? []) {
        if (!found.includes(id)) found.push(id);
      }
    }
  }
  return found;
}

/** The option ids in the Pareto set, from the option search (empty before it runs). */
export function paretoIds(state: RunState): string[] {
  return state.results.searchOptions?.pareto_option_ids ?? [];
}
