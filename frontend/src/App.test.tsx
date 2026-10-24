import { render, screen } from "@testing-library/react";
import { afterEach, vi } from "vitest";
import App from "./App";
import { STAGES } from "./components/layout/stages";

afterEach(() => vi.unstubAllGlobals());

function stubFetch(ok: boolean) {
  const body = { status: "ok", version: "0.1.0", data_dir_found: true, golden_found: true };
  vi.stubGlobal(
    "fetch",
    vi.fn(() => (ok ? Promise.resolve(new Response(JSON.stringify(body))) : Promise.reject(new Error("offline")))),
  );
}

test("renders the themed header with title and notice", () => {
  stubFetch(true);
  render(<App />);
  expect(screen.getByRole("heading", { name: "PVR Agent Room" })).toBeInTheDocument();
  expect(screen.getByText("Proof of concept by Sekuen, prepared for Aldar. Illustrative data.")).toBeInTheDocument();
});

test("shows all seven stages and the empty layout areas", () => {
  stubFetch(true);
  render(<App />);
  expect(STAGES).toHaveLength(7);
  for (const stage of STAGES) expect(screen.getByText(stage.label)).toBeInTheDocument();
  for (const area of ["Evidence", "Agent Room", "Timeline", "Analysis"]) {
    expect(screen.getByRole("region", { name: area })).toBeInTheDocument();
  }
});

test("reports backend status from the health check", async () => {
  stubFetch(true);
  render(<App />);
  expect(await screen.findByText("Backend connected")).toBeInTheDocument();
});

test("reports an unreachable backend", async () => {
  stubFetch(false);
  render(<App />);
  expect(await screen.findByText("Backend not reachable")).toBeInTheDocument();
});
