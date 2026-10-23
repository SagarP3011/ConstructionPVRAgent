# PVR Agent Room: starter kit

Everything Claude Code needs to build the proof of concept.

| File or folder | What it is |
|---|---|
| `SPEC.md` | Full build specification, split into phases with checkpoints |
| `CLAUDE.md` | Working rules Claude Code reads automatically (one phase at a time, ask before committing) |
| `data/` | Fictional project data: bill of quantities, schedule, contract, documents, rates, three change types |
| `tests_golden/golden.json` | Expected results computed from the data, for six cases across the three change types |

## Steps
1. Install Python 3.11+, Node.js 20+, Git, VS Code and the Claude Code extension.
2. Create an empty folder (for example `pvr-agent-room`) and copy everything from this kit into it.
3. In that folder: `git init`, then `git add -A && git commit -m "Starter kit"`.
4. Create `.env` with `OPENAI_API_KEY=...` and `OPENAI_MODEL=...` (a strong model with tool calling). Never commit it.
5. Open the folder in VS Code and start Claude Code.
6. Prompt: "Read CLAUDE.md and SPEC.md. Implement Phase 0 only and follow the checkpoint protocol."
7. When Claude asks "Checkpoint 0 reached, all tests pass. Shall I commit?", check the app yourself (`make dev`), then answer yes.
8. Next prompt: "Implement Phase 1 only and follow the checkpoint protocol." Continue up to Phase 6. Phase 7 is optional.
9. Before the meeting: make sure the replay fixtures from Phase 4 exist, and rehearse with section 17 of `SPEC.md`.

If a phase goes wrong, roll back to the last checkpoint with `git reset --hard HEAD` (discards uncommitted work) and ask again.
