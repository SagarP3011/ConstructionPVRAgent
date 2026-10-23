# Instructions for Claude Code

You are building the PVR Agent Room proof of concept described in `SPEC.md`.

## How to work
1. Read `SPEC.md` fully before writing any code.
2. Implement **only the phase named in the user's message** (section 16 of `SPEC.md`). Never start the next phase on your own.
3. Follow the checkpoint protocol in section 16.0 at the end of every phase:
   - run `make test` (and the phase's CLI or live check) and fix failures,
   - report each checkpoint item as done or not done, the files changed, and anything skipped or questionable,
   - when everything passes, ask: "Checkpoint N reached, all tests pass. Shall I commit?",
   - commit only after the user says yes: `git add -A` then `git commit -m "Checkpoint N: <phase name>"`, after checking `.env` is not staged,
   - never push unless the user explicitly asks,
   - stop and wait.

## Hard rules
- `data/` and `tests_golden/golden.json` are given. Never edit them. If they look inconsistent, stop and report.
- Every number shown to a user comes from a deterministic engine through a tool. The language model never computes numbers that are displayed.
- Never put golden or expected values into engine code or agent prompts. Prompts stay generic across change types.
- No agent frameworks (no LangChain, LangGraph, CrewAI, AutoGen). Use our own orchestrator and agent loop as specified.
- Agent prompts describe role, goal, tools and message format. They must not script a fixed sequence of tool calls.
- Nothing executes before human approval. Keep the test that proves it.
- Secrets only in `.env` (git-ignored). Never print or log the API key.
- Do not use or recreate the Aldar logo. Theme colours and font only, as in section 12.1.

## Style
- Python: type hints, Pydantic v2 models, small pure functions in `engines/`, docstrings, no hidden global state except the explicit registries.
- TypeScript: strict mode, typed event payloads shared in `src/api/events.ts`, small focused components.
- Clear, simple English in all UI text.
- Prefer explicit, readable code over clever abstractions.
