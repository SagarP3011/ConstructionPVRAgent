import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { ReactNode } from "react";
import { afterEach, vi } from "vitest";
import type { RunEvent } from "../api/events";
import { initialRunState, reduceEvents, type RunState } from "../state/runStore";
import { RoomProvider, type RoomValue } from "../state/RoomContext";
import { DecisionPanel } from "./decision/DecisionPanel";
import { captionFor } from "./layout/StageCaption";
import { TraceDrawer } from "./trace/TraceDrawer";
import { WhatIfControls } from "./whatif/WhatIfControls";

afterEach(() => vi.unstubAllGlobals());

const REPO = resolve(__dirname, "../../..");
const PROJECT = JSON.parse(readFileSync(resolve(REPO, "data/project.json"), "utf-8"));
const SCENARIO = JSON.parse(readFileSync(resolve(REPO, "data/scenario.json"), "utf-8"));

function wallEvents(): RunEvent[] {
  return readFileSync(resolve(REPO, "fixtures/demo_run_wall_height.jsonl"), "utf-8")
    .split("\n")
    .filter((l) => l.trim())
    .map((l) => JSON.parse(l) as RunEvent);
}

function wallState(): RunState {
  return reduceEvents(initialRunState(), wallEvents());
}

/** The wall run up to the approval request, as a replay that stops at the decision sees it. */
function wallAtDecision(): RunState {
  const events = wallEvents();
  return reduceEvents(initialRunState(), events.slice(0, events.findIndex((e) => e.type === "approval.requested") + 1));
}

const STATE = wallState();

function inRoom(children: ReactNode, overrides: Partial<RoomValue> = {}) {
  const selection = {
    contractClauses: [],
    selectedFactId: null,
    selectFact: () => {},
    selectedClause: null,
    selectClause: () => {},
  };
  const value: RoomValue = {
    ...selection,
    state: STATE,
    isReplay: true,
    decisionReplay: false,
    speed: 1,
    project: PROJECT,
    agentFilter: null,
    setAgentFilter: () => {},
    openTrace: () => {},
    ...overrides,
  };
  return render(
    <RoomProvider value={value} selection={selection}>
      {children}
    </RoomProvider>,
  );
}

test("what-if re-runs the same change with a new contingency, keeping contractor mode at the default size", async () => {
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(JSON.stringify(SCENARIO.change_types)))));
  const onRerun = vi.fn(() => Promise.resolve());
  inRoom(<WhatIfControls liveAvailable onRerun={onRerun} />);
  fireEvent.click(screen.getByRole("button", { name: /What-if/ }));
  const contingency = await screen.findByLabelText("Cost contingency (AED)");
  expect(contingency).toHaveValue(PROJECT.cost_contingency_remaining_aed);
  fireEvent.change(contingency, { target: { value: "75000" } });
  await waitFor(() => expect(screen.getByRole("button", { name: "Re-run agents" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "Re-run agents" }));
  await waitFor(() => expect(onRerun).toHaveBeenCalledOnce());
  expect(onRerun).toHaveBeenCalledWith({
    change_type: "wall_height",
    parameters: { new_height_m: 2.5 },
    mode: "contractor_pvr",
    overrides: { cost_contingency_remaining_aed: 75000, time_buffer_working_days: null },
  });
});

test("what-if switches to an internal what-if when the size changes", async () => {
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(JSON.stringify(SCENARIO.change_types)))));
  const onRerun = vi.fn(() => Promise.resolve());
  inRoom(<WhatIfControls liveAvailable onRerun={onRerun} />);
  fireEvent.click(screen.getByRole("button", { name: /What-if/ }));
  fireEvent.change(await screen.findByLabelText("New wall height (m)"), { target: { value: "3" } });
  fireEvent.click(screen.getByRole("button", { name: "Re-run agents" }));
  await waitFor(() => expect(onRerun).toHaveBeenCalledOnce());
  expect(onRerun).toHaveBeenCalledWith(
    expect.objectContaining({ parameters: { new_height_m: 3 }, mode: "internal_what_if" }),
  );
});

test("the trace shows model use and filters events", () => {
  inRoom(<TraceDrawer open focusToolCall={null} onClose={() => {}} onClearFocus={() => {}} />);
  const trace = screen.getByRole("complementary", { name: "Trace" });
  expect(within(trace).getByText("Model calls", { selector: "dt" }).nextSibling).toHaveTextContent(String(STATE.llm.calls));
  fireEvent.change(within(trace).getByLabelText("Search events"), { target: { value: "run_cpm" } });
  const rows = within(trace).getAllByRole("listitem");
  expect(rows.length).toBeGreaterThan(0);
  for (const row of rows) expect(row).toHaveTextContent(/run_cpm/);
});

test("the trace can focus on the tool call behind a fact", () => {
  const fact = Object.values(STATE.facts).find((f) => f.tool === "price_change" && f.path === "direct_cost_aed");
  expect(fact).toBeDefined();
  inRoom(<TraceDrawer open focusToolCall={fact?.tool_call_id ?? null} onClose={() => {}} onClearFocus={() => {}} />);
  const trace = screen.getByRole("complementary", { name: "Trace" });
  expect(within(trace).getByText(/Showing tool call/)).toBeInTheDocument();
  const rows = within(trace).getAllByRole("listitem");
  // The call, its result and every fact it registered.
  const expected = STATE.events.filter(
    (e) => (e.payload as { tool_call_id?: string }).tool_call_id === fact?.tool_call_id,
  ).length;
  expect(rows).toHaveLength(Math.min(expected, 300));
  expect(within(trace).getByText(fact?.tool_call_id ? new RegExp(`${fact.tool_call_id} price_change ok`) : /x/)).toBeInTheDocument();
});

test("a replay that stops at the decision lets the viewer choose; a recorded replay does not", () => {
  const atDecision = wallAtDecision();
  const options = (atDecision.finalOptions ?? []).map((o) => o.option_id);
  expect(options.length).toBeGreaterThan(1);

  const { unmount } = inRoom(<DecisionPanel />, { state: atDecision, decisionReplay: true });
  expect(screen.getByText("Replay paused: waiting for your decision")).toBeInTheDocument();
  for (const id of options) expect(screen.getByRole("button", { name: new RegExp(id) })).toBeEnabled();
  expect(screen.getByRole("button", { name: "Approve" })).toBeDisabled(); // needs an option, a name and a role
  fireEvent.click(screen.getByRole("button", { name: new RegExp(options[0]!) }));
  fireEvent.change(screen.getByLabelText("Your name"), { target: { value: "Dana Ali" } });
  fireEvent.change(screen.getByLabelText("Your role"), { target: { value: "Project Director" } });
  expect(screen.getByRole("button", { name: "Approve" })).toBeEnabled();
  unmount();

  inRoom(<DecisionPanel />, { state: atDecision, decisionReplay: false });
  expect(screen.getByText("Replay: the recorded decision follows")).toBeInTheDocument();
  for (const id of options) expect(screen.getByRole("button", { name: new RegExp(id) })).toBeDisabled();
});

test("the caption says in plain words what is happening now", () => {
  expect(captionFor(initialRunState(), false)?.title).toBe("Starting");
  expect(captionFor({ ...initialRunState(), status: "running", stage: "debate" }, false)?.title).toMatch(/debate/);
  expect(captionFor(wallAtDecision(), false)?.title).toBe("Waiting for a person to decide");
  expect(captionFor(wallAtDecision(), true)?.title).toBe("The recorded decision follows");
  expect(captionFor(STATE, false)?.title).toMatch(/approved/);
});
