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

`run` also takes `--param name=value`, `--mode internal_what_if|contractor_pvr`, and for unattended use
`--approve OPT-... --approver "Name" --role "Role"` or `--reject "reason"`. Each run writes its full event trace to
`runs/<run_id>/events.jsonl`; approved actions write their files to `runs/<run_id>/outputs/`.

## API (backend on :8000)

| Method and path | Purpose |
|---|---|
| `GET /api/health` | Health check; `live_runs_available` says whether an API key is set |
| `GET /api/change-types`, `GET /api/data/{name}` | Change types and data files |
| `POST /api/runs` | Start a live run: `{"change_type": "...", "parameters": {...}, "mode": "...", "overrides": {...}}` |
| `GET /api/runs/{id}/events` | Server-Sent Events: the run's events live (history first) |
| `GET /api/runs/{id}` | Run state snapshot (also for stored runs and fixtures) |
| `POST /api/runs/{id}/approve` | `{"option_id", "action_ids", "approver_name", "approver_role"}` |
| `POST /api/runs/{id}/reject` | `{"approver_name", "approver_role", "reason"}` |
| `GET /api/runs/{id}/outputs/{file}` | Files written by approved actions |
| `GET /api/runs` | Fixtures and stored runs |
| `GET /api/replay/{id}?speed=1.0&max_gap=3` | SSE replay of a stored run or fixture with its original timing; needs no API key |

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

## Build status

Built in phases (SPEC section 16). Phases 0 to 5 are in place: scaffold, deterministic engines, tools and facts,
the full multi-agent orchestration, the API with live streaming, run store and replay (fixtures in `fixtures/`), and
the web app: change selector, Agent Room, evidence, analysis tabs, decision and outputs, for live runs and replays.

For a demo, serve the production build (smoother than the dev server): `npm run build` then `npx vite preview` in
`frontend/`, with the backend running; open http://localhost:4173.
