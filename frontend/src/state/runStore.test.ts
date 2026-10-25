import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { RunEvent } from "../api/events";
import { citedClauses, initialRunState, reduceEvents, visibleTimeline } from "./runStore";

const REPO = resolve(__dirname, "../../..");
const golden = JSON.parse(readFileSync(resolve(REPO, "tests_golden/golden.json"), "utf-8")) as {
  baseline: { completion_working_day: number };
};

function loadFixture(changeType: string): RunEvent[] {
  return readFileSync(resolve(REPO, `fixtures/demo_run_${changeType}.jsonl`), "utf-8")
    .split("\n")
    .filter((line) => line.trim())
    .map((line) => JSON.parse(line) as RunEvent);
}

function inBatches(events: RunEvent[], size: number) {
  let state = initialRunState();
  for (let i = 0; i < events.length; i += size) state = reduceEvents(state, events.slice(i, i + size));
  return state;
}

function ofType<T extends RunEvent["type"]>(events: RunEvent[], type: T) {
  return events.filter((e): e is Extract<RunEvent, { type: T }> => e.type === type);
}

describe.each(["wall_height", "road_widening", "paving_area"])("replaying %s", (changeType) => {
  const events = loadFixture(changeType);
  const state = inBatches(events, 97);

  test("ends approved, with every stage done and the recorded decision", () => {
    expect(state.status).toBe("completed");
    expect(state.stagesDone).toEqual(expect.arrayContaining(["intake", "assessment", "commercial", "debate", "synthesis", "action"]));
    const granted = ofType(events, "approval.granted")[0];
    expect(state.decision).toEqual(granted?.payload);
    expect(state.executed.map((e) => e.action_id)).toEqual(ofType(events, "action.executed").map((e) => e.payload.action_id));
    for (const e of state.executed) expect(state.actions[e.action_id]?.status).toBe("executed");
    expect(Object.values(state.agents).every((a) => !a.active)).toBe(true);
  });

  test("keeps every message, fact and tool call the events carried", () => {
    expect(Object.keys(state.messages)).toHaveLength(ofType(events, "message.posted").length);
    expect(Object.keys(state.facts)).toHaveLength(ofType(events, "fact.registered").length);
    expect(Object.keys(state.tools)).toHaveLength(ofType(events, "tool.called").length);
    expect(state.eventCount).toBe(events.length);
    expect(state.lastEventId).toBe(events[events.length - 1]?.event_id);
  });

  test("panel values are the tool results, unchanged", () => {
    const price = ofType(events, "tool.result").find((e) => e.payload.tool === "price_change" && e.payload.ok);
    expect(state.results.price).toEqual(price?.payload.result);
    expect(state.results.baselineCpm?.completion_working_day).toBe(golden.baseline.completion_working_day);
    const final = ofType(events, "options.final")[0];
    expect(state.finalOptions).toEqual(final?.payload.options);
    expect(state.results.searchOptions?.pareto_option_ids).toBeDefined();
  });

  test("stances follow stance.changed and the final stances", () => {
    const final = ofType(events, "options.final")[0]?.payload.stances ?? {};
    for (const [agent, stance] of Object.entries(final)) {
      if (stance) expect(state.agents[agent as keyof typeof state.agents].stance).toBe(stance);
    }
    const changes = ofType(events, "stance.changed");
    const histories = Object.values(state.agents).reduce((n, a) => n + a.stanceHistory.length, 0);
    expect(histories).toBe(changes.length);
  });

  test("a corrected message replaces its original in the timeline", () => {
    const timeline = visibleTimeline(state, null);
    const shownIds = timeline.filter((i) => i.kind === "message").map((i) => i.id);
    for (const corrected of ofType(events, "message.corrected")) {
      expect(state.messages[corrected.payload.original_message_id]?.superseded_by).toBe(corrected.payload.corrected_message_id);
      expect(shownIds).toContain(corrected.payload.original_message_id);
      expect(shownIds).not.toContain(corrected.payload.corrected_message_id);
    }
  });

  test("batch size does not change the result", () => {
    // Small batches (a live stream flushes every 40 ms) against one batch for the whole run.
    const small = inBatches(events, 13);
    const allAtOnce = inBatches(events, events.length);
    expect(allAtOnce).toEqual(small);
    expect(state).toEqual(small);
  }, 30_000);

  test("cited clauses are found in message text", () => {
    expect(citedClauses(state).length).toBeGreaterThan(0);
  });
});

function deepFreeze<T>(value: T): T {
  if (value && typeof value === "object" && !Object.isFrozen(value)) {
    Object.freeze(value);
    for (const child of Object.values(value as object)) deepFreeze(child);
  }
  return value;
}

test("no batch writes to the state it was given (deep-frozen before every batch)", () => {
  const events = loadFixture("wall_height");
  let state = initialRunState();
  for (let i = 0; i < events.length; i += 50) state = reduceEvents(deepFreeze(state), events.slice(i, i + 50));
  expect(state.status).toBe("completed");
}, 30_000);

test("reduceEvents never changes the state it is given", () => {
  const events = loadFixture("paving_area");
  const before = reduceEvents(initialRunState(), events.slice(0, 200));
  const snapshot = JSON.stringify(before);
  reduceEvents(before, events.slice(200));
  expect(JSON.stringify(before)).toBe(snapshot);
});

test("the agent filter keeps that agent's messages and tool calls only", () => {
  const state = reduceEvents(initialRunState(), loadFixture("wall_height"));
  const items = visibleTimeline(state, "cost");
  expect(items.length).toBeGreaterThan(0);
  for (const item of items) {
    if (item.kind === "tool") expect(state.tools[item.id]?.agent).toBe("cost");
    if (item.kind === "message") {
      const m = state.messages[item.id];
      const shown = m?.superseded_by ? state.messages[m.superseded_by] : m;
      expect([shown?.from, shown?.to]).toContain("cost");
    }
    expect(item.kind).not.toBe("stage");
  }
});

test("a fatal error fails the run", () => {
  const state = reduceEvents(initialRunState(), [
    { event_id: "E-1", run_id: "R-x", type: "run.started", ts: "", payload: { context: { change_type: "paving_area", parameters: {}, mode: "internal_what_if", overrides: { cost_contingency_remaining_aed: null, time_buffer_working_days: null } }, kind: "full" } },
    { event_id: "E-2", run_id: "R-x", type: "run.error", ts: "", payload: { error: "model fell over", fatal: true, stage: "intake" } },
  ]);
  expect(state.status).toBe("failed");
  expect(state.errors[0]?.error).toBe("model fell over");
});
