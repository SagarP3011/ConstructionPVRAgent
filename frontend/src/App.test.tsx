import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, vi } from "vitest";
import App from "./App";
import { STAGES } from "./components/layout/stages";

afterEach(() => vi.unstubAllGlobals());

const CHANGE_TYPES = [
  { id: "wall_height", title: "Raise the boundary wall", element: "boundary_wall", fixed: {}, has_contractor_claim_at_default: true,
    default_instruction: "Raise the wall to {new_height_m} m.", modes: ["contractor_pvr", "internal_what_if"],
    parameters: [{ name: "new_height_m", label: "New wall height (m)", default: 2.5, min: 2.1, max: 3.0, step: 0.1 }] },
  { id: "road_widening", title: "Widen the internal road", element: "internal_road", fixed: {}, has_contractor_claim_at_default: false,
    default_instruction: "Widen by {widen_by_m} m.", modes: ["internal_what_if"],
    parameters: [{ name: "widen_by_m", label: "Extra road width (m)", default: 1, min: 0.5, max: 2, step: 0.5 }] },
  { id: "paving_area", title: "Add paving area", element: "hardscape", fixed: {}, has_contractor_claim_at_default: false,
    default_instruction: "Add {added_area_m2} m2.", modes: ["internal_what_if"],
    parameters: [{ name: "added_area_m2", label: "Extra paving (m2)", default: 400, min: 100, max: 1500, step: 50 }] },
];

function stubBackend(ok: boolean, liveRuns = true, interpretation: unknown = null) {
  const bodies: Record<string, unknown> = {
    "/api/health": { status: "ok", version: "0.1.0", data_dir_found: true, golden_found: true, live_runs_available: liveRuns },
    "/api/change-types": CHANGE_TYPES,
    "/api/runs": [{ id: "demo_run_paving_area", source: "fixture", run_id: "R-1", kind: "full", state: "completed", live: false,
      change_type: "paving_area", parameters: { added_area_m2: 400 }, mode: "internal_what_if", overrides: null, started_at: "2026-10-25T08:00:00Z",
      ended_at: null, event_count: 900, chosen_option: "OPT-NONE" }],
    "/api/data/project": { name: "Al Noor Gardens", employer_commitment_working_day: 107 },
    "/api/data/contract": { contract_ref: "C", clauses: [{ clause: "13.3", title: "Valuation of Variations", text: "..." }] },
    "/api/data/boq": [],
    "/api/interpret": interpretation,
  };
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) =>
      ok && url in bodies ? Promise.resolve(new Response(JSON.stringify(bodies[url]))) : Promise.reject(new Error("offline")),
    ),
  );
}

test("renders the themed header with title and notice", () => {
  stubBackend(true);
  render(<App />);
  expect(screen.getByRole("heading", { name: "PVR Agent Room" })).toBeInTheDocument();
  expect(screen.getByText("Proof of concept by Sekuen, prepared for Aldar. Illustrative data.")).toBeInTheDocument();
  expect(STAGES).toHaveLength(7);
  for (const stage of STAGES) expect(screen.getByText(stage.label)).toBeInTheDocument();
});

test("the start screen offers the three changes and the saved runs", async () => {
  stubBackend(true);
  render(<App />);
  expect(await screen.findByRole("button", { name: /Raise the boundary wall/ })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Widen the internal road/ })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Add paving area/ })).toBeInTheDocument();
  expect(await screen.findByRole("button", { name: "Replay" })).toBeInTheDocument();
});

test("choosing a change shows its size, mode and instruction", async () => {
  stubBackend(true);
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: /Raise the boundary wall/ }));
  expect(await screen.findByLabelText("New wall height (m)")).toBeInTheDocument();
  expect(screen.getByText("Raise the wall to 2.5 m.")).toBeInTheDocument();
  expect(screen.getByLabelText(/Contractor PVR/)).toBeChecked();
  expect(screen.getByRole("button", { name: "Run agents" })).toBeEnabled();
});

test("without an API key, live runs are disabled and replays stay available", async () => {
  stubBackend(true, false);
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: /Add paving area/ }));
  expect(await screen.findByRole("button", { name: "Run agents" })).toBeDisabled();
  expect(screen.getByText(/Saved runs can still be replayed/)).toBeInTheDocument();
});

test("reports backend status from the health check", async () => {
  stubBackend(true);
  render(<App />);
  expect(await screen.findByText("Backend connected")).toBeInTheDocument();
});

test("reports an unreachable backend", async () => {
  stubBackend(false);
  render(<App />);
  expect(await screen.findByText("Backend not reachable")).toBeInTheDocument();
});

test("a typed request is read, confirmed and fills in the change and its size", async () => {
  stubBackend(true, true, {
    status: "interpreted", change_type: "road_widening", title: "Widen the internal road",
    parameters: { widen_by_m: 1.5 }, mode: "internal_what_if", instruction_text: "Widen by 1.5 m.",
    reading: "A wider internal road for a drop-off lane.", reason: "",
  });
  render(<App />);
  fireEvent.change(await screen.findByLabelText("Describe the change in your own words"), {
    target: { value: "widen the road by one and a half metres" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Read my request" }));
  expect(await screen.findByText("A wider internal road for a drop-off lane.", { exact: false })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Yes, use this" }));
  expect(await screen.findByLabelText("Extra road width (m)")).toHaveValue("1.5");
  expect(screen.getByText("Widen by 1.5 m.", { selector: "p.text-sm.leading-relaxed" })).toBeInTheDocument();
});

test("a request outside the three changes is declined politely", async () => {
  stubBackend(true, true, { status: "declined", change_type: null, title: null, parameters: {}, mode: null,
    instruction_text: null, reading: "", reason: "I can only assess the wall, road or paving changes." });
  render(<App />);
  fireEvent.change(await screen.findByLabelText("Describe the change in your own words"), {
    target: { value: "build a swimming pool" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Read my request" }));
  expect(await screen.findByText(/I can only assess the wall, road or paving changes/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Run agents" })).not.toBeInTheDocument();
});

test("a saved run of the same change and size can be replayed at no cost", async () => {
  stubBackend(true);
  render(<App />);
  await screen.findByRole("button", { name: "Replay" });
  fireEvent.click(screen.getByRole("button", { name: /Add paving area/ }));
  expect(await screen.findByRole("button", { name: "Replay saved run (no cost)" })).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Extra paving (m2)"), { target: { value: "450" } });
  expect(screen.queryByRole("button", { name: "Replay saved run (no cost)" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /Raise the boundary wall/ }));
  expect(screen.queryByRole("button", { name: "Replay saved run (no cost)" })).not.toBeInTheDocument();
});
