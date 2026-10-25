# PVR Agent Room

Proof of concept by Sekuen, prepared for Aldar. Illustrative data.

A multi-agent system that assesses a PVR (potential variation request): seven agents assess a scope change,
debate the options and prepare a decision for a person to approve. Numbers come from deterministic engines;
agents reason about them; people approve. See `SPEC.md` for the full specification.

## Requirements

- Python 3.11 or newer (setup prefers 3.12 when several versions are installed)
- Node.js 20 or newer, with npm
- Git
- An OpenAI API key and a model that supports tool calling

## First-time setup

1. Copy `.env.example` to `.env` and fill in `OPENAI_API_KEY` and `OPENAI_MODEL`. Never commit `.env`.
2. Install everything:

   | Windows (PowerShell) | macOS / Linux |
   |---|---|
   | `powershell -ExecutionPolicy Bypass -File scripts\setup.ps1` | `make setup` |

   This creates `backend/.venv`, installs the backend (pinned in `backend/pyproject.toml`) and
   runs `npm ci` in `frontend/`.

3. Check the OpenAI connection (the key is never printed):

   ```
   backend\.venv\Scripts\python.exe -m pvr.cli check-llm      # Windows, run from backend\
   make check-llm                                              # macOS / Linux
   ```

   It confirms the key works, that `OPENAI_MODEL` is available to your key, and that it supports tool calling.

## Daily commands

| Task | Windows (PowerShell) | macOS / Linux |
|---|---|---|
| Run backend (:8000) and frontend (:5173) | `powershell -ExecutionPolicy Bypass -File scripts\dev.ps1` | `make dev` |
| Tests (pytest without live tests, tsc, vitest) | `powershell -ExecutionPolicy Bypass -File scripts\test.ps1` | `make test` |
| Live tests (calls OpenAI) | `powershell -ExecutionPolicy Bypass -File scripts\test.ps1 -Live` | `make test-live` |

Then open http://localhost:5173. The backend health check is at http://127.0.0.1:8000/api/health.
Press Ctrl+C in the dev window to stop both servers.

## Layout

- `data/`, `tests_golden/golden.json`: given inputs and expected values. Do not edit. The backend reads them
  from the repository root.
- `backend/pvr/`: FastAPI app, engines, tools, agents, orchestrator, events, CLI.
- `frontend/`: React + TypeScript + Vite + Tailwind CSS app. Theme tokens in `frontend/src/theme/tokens.css`.
- `scripts/`: PowerShell equivalents of the Makefile targets.
- `runs/`: generated run folders (git-ignored). `fixtures/`: recorded demo runs for replay.

## Console commands (from `backend\`)

| Command | What it does |
|---|---|
| `.venv\Scripts\python.exe -m pvr.cli engines` | Deterministic assessment of the three default changes (no LLM) |
| `.venv\Scripts\python.exe -m pvr.cli agent cost --change wall_height` | One agent alone, live |
| `.venv\Scripts\python.exe -m pvr.cli run --change wall_height` | Full seven-agent run; pauses for your approval, then executes the approved actions |
| `.venv\Scripts\python.exe -m pvr.cli save-fixture R-...` | Save a completed, approved run as `fixtures/demo_run_<change_type>.jsonl` (plus its outputs) |
| `.venv\Scripts\python.exe -m pvr.cli save-fixture R-... --name wall_3m` | Save a variant as `fixtures/demo_run_wall_3m.jsonl`, next to the default demo runs |
| `.venv\Scripts\python.exe -m pvr.cli engines --change wall_height --contingency 75000` | Deterministic what-if check (also `--time-buffer DAYS`), no LLM |

`run` also takes `--param name=value`, `--mode internal_what_if|contractor_pvr`, and for unattended use
`--approve OPT-... --approver "Name" --role "Role"` or `--reject "reason"`. Each run writes its full event trace to
`runs/<run_id>/events.jsonl`; approved actions write their files to `runs/<run_id>/outputs/`.

## API (backend on :8000)

| Method and path | Purpose |
|---|---|
| `GET /api/health` | Health check; `live_runs_available` says whether an API key is set |
| `GET /api/change-types`, `GET /api/data/{name}` | Change types and data files |
| `POST /api/interpret` | Free-text change input: `{"text": "..."}`; the Intake agent maps it to a change type and sizes, or declines |
| `POST /api/runs` | Start a live run: `{"change_type": "...", "parameters": {...}, "mode": "...", "overrides": {...}}` |
| `GET /api/runs/{id}/events` | Server-Sent Events: the run's events live (history first) |
| `GET /api/runs/{id}` | Run state snapshot (also for stored runs and fixtures) |
| `POST /api/runs/{id}/approve` | `{"option_id", "action_ids", "approver_name", "approver_role"}` |
| `POST /api/runs/{id}/reject` | `{"approver_name", "approver_role", "reason"}` |
| `GET /api/runs/{id}/outputs/{file}` | Files written by approved actions |
| `GET /api/runs` | Fixtures and stored runs |
| `GET /api/replay/{id}?speed=1.0&max_gap=3` | SSE replay of a stored run or fixture with its original timing; needs no API key |
| `POST /api/replay/{id}/decision` | Bring a recorded run back to its approval gate as a new run, so a person decides again; replay that run, then approve or reject it like a live run. Needs no API key |

Each SSE message is one event (`id:` is the event id, `data:` the event JSON). A stream ends with a named `end`
event. To resume, send `Last-Event-ID` (or `?after=E-...`); replay accepts the same, so a client can change speed
mid-replay by reconnecting. Replay caps each pause at `max_gap` seconds (before speed) so slow model calls and the
approval wait do not stall the demo; `max_gap=0` gives the exact original timing.

Watch a live run from a terminal:

```
curl -s -X POST http://127.0.0.1:8000/api/runs -H "Content-Type: application/json" -d "{\"change_type\":\"paving_area\"}"
curl -N http://127.0.0.1:8000/api/runs/<run_id>/events
```

A run waiting for approval is held in server memory; after a restart its trace remains but it can no longer be
approved.

## Live or saved: keeping model costs down

A full seven-agent run calls the model about 30 to 55 times (roughly 150,000 to 300,000 prompt tokens). Every
completed run is stored in `runs/` and can be replayed exactly, with no model calls, from **Replay a saved run**.
When the change, size and mode you choose match a saved run, the start screen also offers **Replay saved run
(no cost)** next to **Run agents**. A replay plays the recording up to the decision and then stops: the person in
the room chooses any presented option and approves, and the outputs are written for that choice. The step after
approval is code only, so this needs no model calls either. (A recording that never reached a decision plays as
recorded.) Recommended: record the runs you plan to show once (`save-fixture`, with
`--name` for variants), present those as replays, and run live only for a change the audience asks for.

Typed requests ("Describe the change in your own words") cost one small model call each. The Intake agent only
picks the change type and copies the sizes from the text; code works out relative sizes ("half a metre higher"),
checks them against the allowed ranges and fills the instruction. Nothing runs until the person confirms.

## Demo script (about 15 minutes)

Before the meeting: start the backend and the production build of the frontend (see Build status), open
http://localhost:4173 and check the header says "Backend connected". If there is no OpenAI key or credit, everything
below except steps 2 and 9 works from the recorded demo runs ("Replay a saved run").

1. **Start screen.** Show the contract clauses and the BOQ (bill of quantities) under Project data. Say: "Choose a
   change, and set its size."
2. **Let Aldar pick.** Pick a card, or let them type the change in their own words and confirm the reading. If they
   have no preference: Raise the boundary wall, 2.5 m, Contractor PVR mode. Click **Run agents**, or **Replay saved
   run (no cost)**.
   On first open a short guide, "What am I looking at?", explains the screen; reopen it with **?** in the header. The
   run opens in the simple view (agents, timeline, what is happening now, decision); **Show details** adds the
   evidence, the Cost, Schedule, Buffer and Options tabs and What-if. Use details for steps 4 to 6 and 9.
3. **Agent Room.** Point at Intake, then Contract, Cost and Time working in parallel (pulsing nodes, tool sparks), and
   an agent asking another a question (a "?" flying between them, an Answer in the timeline).
4. **Schedule tab.** Added days against float: the wall chain has 14 added days, 6 of them absorbed by float, so
   completion moves to day 95. Baseline bars are thin grey; markers show contract completion, the impacted
   completion and the Employer's commitment.
5. **Debate.** Challenges in the timeline and stance badges changing under Cost, Time and Commercial. Options tab:
   every option the agents evaluated, with the Pareto set highlighted.
6. **Verification.** A Verifier tick on each message. Click any claim chip: the drawer shows the tool call and field
   the number came from ("Computed by a deterministic engine"). "Show this tool call in the trace" opens the trace
   at that call. Where a message failed a check, the corrected message shows the original struck through.
7. **Decision.** Up to three options with delay, completion, total cost, buffer and contingency left, and the agents
   behind each. Tick the actions, enter a name and role, and approve. Nothing ran before this. On a replay the run
   stops here too, so let Aldar choose the option.
8. **Outputs.** PVR output form (Print to PDF), verification report (contractor mode), tasks and notifications.
9. **A second change.** New change, then Widen the internal road (critical path: every day counts) or Add paving
   area (float absorbs it; the debate ends after one round). Same agents, different analysis. Or use **What-if** to
   re-run the wall at 3.0 m (the buffer breaks without extra crews) or with contingency AED 75,000 (holding the date
   then fits the budget).
10. **Trace.** Open Trace in the header: every event, model call (model, tokens, latency) and fact, with filters and
    a download of the full trace, which replays exactly.

Say plainly: the orchestrator fixes the stages; inside each stage the agents choose their own tools, questions and
positions. Numbers come from code, agents reason about them, people approve.

**Rehearsal checklist:** each live run under 4 minutes; replays work with the network unplugged from OpenAI; no
console errors; every number on screen traceable to a fact; nothing executed before approval.

## Build status

Built in phases (SPEC section 16). Phases 0 to 7 are in place (Phase 7: free-text change input only): scaffold, deterministic engines, tools and facts,
the full multi-agent orchestration, the API with live streaming, run store and replay (fixtures in `fixtures/`), and
the web app: change selector, Agent Room, evidence, analysis tabs, decision and outputs, What-if re-runs and the
trace drawer, for live runs and replays.

For a demo, serve the production build (smoother than the dev server): `npm run build` then `npx vite preview` in
`frontend/`, with the backend running; open http://localhost:4173.
