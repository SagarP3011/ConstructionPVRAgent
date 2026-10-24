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

`run` also takes `--param name=value`, `--mode internal_what_if|contractor_pvr`, and for unattended use
`--approve OPT-... --approver "Name" --role "Role"` or `--reject "reason"`. Each run writes its full event trace to
`runs/<run_id>/events.jsonl`; approved actions write their files to `runs/<run_id>/outputs/`.

## Build status

Built in phases (SPEC section 16). Phases 0 to 3 are in place: scaffold, deterministic engines, tools and facts,
and the full multi-agent orchestration in the console.
