# PVR Agent Room: Build Specification

Proof of concept (PoC) built by Sekuen to show Aldar a working multi-agent system for assessing a potential variation request (PVR).
This document is the single source of truth for building it. It is written for Claude Code and is executed **one phase at a time** (section 16).

---

## 0. How to use this document

- Read the whole document once, then implement **only the phase you are asked to implement**.
- Every phase ends with a **checkpoint**: acceptance criteria that must all pass. Follow the checkpoint protocol in section 16.0 (test, report, ask before committing, stop).
- The data files in `data/` and the expected values in `tests_golden/golden.json` are given. Do not change them. If something in them looks wrong, stop and report it.
- When this document and your own judgement disagree, follow this document and flag the disagreement.

---

## 1. Goal

### 1.1 What we are proving

Aldar plans a PVR tool: when a scope change happens on a project, the tool must work out the cost impact and the time impact, check the contract, and help people decide what to do. Aldar asked any partner to show three things:

1. A real **multi-agent** system where agents debate and take actions, not a single chatbot.
2. The **UI and UX** quality we deliver.
3. That we can build fast and correctly.

This PoC shows all three. The user picks one of three scope changes, sets its size, and watches seven agents assess it, debate it and prepare a decision for a person to approve. It is a capability demonstration, not Aldar's product. Aldar's real tool will follow Aldar's own design.

### 1.2 The core rule

**Numbers come from code. Agents reason, argue and decide what to do with those numbers. People approve.**

- Every quantity, cost, duration and date shown anywhere must come from a deterministic engine (section 7), reached through a tool (section 8).
- The language model never does arithmetic that ends up on screen.
- A Verifier agent checks every number an agent states against the tool results. Unsupported numbers are rejected.
- No action takes effect until a named person approves it.

### 1.3 What "agentic" must mean here (non-negotiable)

If we call this agentic, all of these must be true and visible in the UI and the trace:

| # | Property | Evidence required |
|---|---|---|
| P1 | Agents choose their own tools and arguments | Trace shows tool calls chosen by the model; agent code contains no hardcoded tool-call sequence |
| P2 | Agents talk to each other | Directed questions between agents (`ask_agent`) and challenges in the debate, drawn as live edges in the Agent Room |
| P3 | Agents change their position in response to others | Each agent's stance is recorded per round; the UI shows stance changes |
| P4 | Independent verification | Every numeric claim links to a tool fact; violations are caught and corrected live |
| P5 | Actions with real effect | Approved actions create files, tasks and notifications in the run folder; nothing is executed before approval |
| P6 | Not scripted | Three different change types, each with adjustable size, produce different analyses, debates and options from the same agents |
| P7 | Full audit trail | Every event is stored and the run can be replayed exactly |

Be honest about the design: the orchestrator fixes the **stages** (guardrails), while agent behaviour **inside** each stage is autonomous. The UI and demo script say this plainly.

---

## 2. Scenarios: three change types

### 2.1 The project

A fictional community project, **Al Noor Gardens, Phase 2: Infrastructure and Landscaping**. One contractor, a remeasurable bill of quantities (BOQ) with 38 lines, a 27-activity programme, and 11 contract clauses. Baseline completion is working day 87 (Wed 3 Feb 2027). The Employer has committed to its own customers for working day 107 (Fri 26 Feb 2027), so it holds a **20 working day time buffer**, and **AED 65,000** of cost contingency remains for this package.

### 2.2 The user chooses one change and its size

| Change type (`change_type`) | Parameters (default, range) | Schedule behaviour | What the demo shows |
|---|---|---|---|
| **Raise the boundary wall** (`wall_height`) | New height: 2.5 m (2.1 to 3.0, step 0.1) | Wall chain has 6 days of float, so delay is **partial** | A real three-way trade-off between cost, time and contingency |
| **Widen the internal road** (`road_widening`) | Extra width: 1.0 m (0.5 to 2.0, step 0.5); length: 600 m (100 to 1,500, step 100) | Roads are on the **critical path**, so added days delay completion | Acceleration is cheap compared with delay; budget uplift is needed in every option |
| **Add paving area** (`paving_area`) | Extra interlocking paving: 400 m2 (100 to 1,500, step 50) | Paving has 14 days of float, so **no delay** | Agents agree quickly; a cost-only decision |

Modes:
- `contractor_pvr`: available only for the wall change at its default 2.5 m. The contractor's PVR-023 (claiming AED 61,419.60 and 21 working days) is checked against the assessment.
- `internal_what_if`: available for all change types and values. The Employer assesses the change before announcing it; no contractor claim is checked.

### 2.3 What the agents must do (all change types)

1. Understand the change (from the instruction text and parameters; for the wall, also from Drawing L-201 Revision B to C).
2. Find the affected BOQ items, and notice the related items that are **not** affected or that **need review**.
3. Price the change at contract rates.
4. Find the affected programme activities, recalculate the critical path and the delay.
5. Check the contract: eligibility, valuation rules, preliminaries, extension of time, time-related costs, acceleration, notice period, design responsibility, new rates.
6. Check the time buffer and cost contingency.
7. Debate the options: accept the delay, or add crews to recover time at extra cost.
8. In `contractor_pvr` mode, verify the contractor's claim against the assessment.
9. Present the best options to a person, who approves one.
10. Execute the approved actions.

### 2.4 Expected results at default values

All values are reproduced in `tests_golden/golden.json` (`cases`), computed from the data files. The golden file also covers wall 3.0 m, road 2.0 m over 1,500 m, and paving 1,500 m2.

**A. Raise the boundary wall to 2.5 m**

| BOQ code | Item | Change |
|---|---|---|
| B-04-010 | Blockwork 200 mm | +200 m2 |
| B-04-015 | Stiffener columns | +2.02 m3 |
| B-04-020 | Plaster, both faces | +400 m2 |
| B-04-040 | Paint, both faces | +400 m2 |
| B-04-030 | Coping | 0 (not affected) |
| B-04-005, B-04-008 | Foundation excavation and footing | Needs review: designed for the previous height; structural check by the design consultant |

Direct cost: **AED 43,529.00**. Added duration: A320 +6, A330 +5, A340 +3 working days (14 in total, but 6 days of float, so 8 days of delay).

| Option | Extra crews | Delay | Completion | Total cost | Buffer left | Contingency left |
|---|---|---|---|---|---|---|
| OPT-A320 (hold the date) | A320 | 0 | 3 Feb 2027 | 69,929 | 20 | **-4,929** (uplift needed) |
| OPT-A340 (balanced) | A340 | 2 | 5 Feb 2027 | 64,129 | 18 | 871 |
| OPT-NONE (accept delay) | none | 8 | 12 Feb 2027 | 63,529 | 12 | 1,471 |

Contractor claim check (`contractor_pvr` mode): claimed AED 61,419.60 (contractor's own rates AED 55,836 plus 10% preliminaries AED 5,583.60) and 21 working days. Assessed AED 43,529.00 at BOQ rates (clause 13.3); preliminaries percentage not allowed (13.4); extension assessed at 8 days without acceleration (8.4); time-related costs at AED 2,500 per day only for an extension actually granted (8.5). Notice given 2 calendar days after the instruction, within 28 days (20.1).

**B. Widen the internal road by 1.0 m over 600 m**

| BOQ code | Item | Change |
|---|---|---|
| R-02-010 | Road excavation | +480 m3 |
| R-02-020, R-02-030, R-02-040, R-02-060, R-02-070 | Subgrade, sub-base, base, binder, wearing course | +600 m2 each |
| R-02-080 | Road markings | 0 (not affected) |
| R-02-050 | Kerbs | Needs review: kerb line moves; removal and re-laying has no BOQ rate, so a new rate must be agreed (clause 13.3) |

Direct cost: **AED 100,440.00**. Added duration: +1 day each on A100, A110, A120, A140, A150, all on the critical path, so 5 days of delay without acceleration.

| Option | Extra crews | Delay | Completion | Total cost | Buffer left | Contingency left |
|---|---|---|---|---|---|---|
| OPT-A120 | A120 | 0 | 3 Feb 2027 | 114,240 | 20 | -49,240 |
| OPT-NONE | none | 5 | 9 Feb 2027 | 112,940 | 15 | -47,940 |

Both options need a budget uplift. Holding the date costs only AED 1,300 more than accepting the delay.

**C. Add 400 m2 of paving**

| BOQ code | Item | Change |
|---|---|---|
| L-05-050 | Interlocking paving | +400 m2 |
| L-05-060 | Granite paving | 0 (not affected) |

Direct cost: **AED 36,800.00**. Added duration: A420 +2 days, absorbed by 14 days of float. One Pareto option: OPT-NONE, no delay, AED 36,800, contingency left AED 28,200. Adding a crew (OPT-A420) costs more for no time benefit.

**Pareto rule:** keep options that no other option beats on both total cost and delay. If two options tie on both, keep the one with fewer extra crews, then the one whose activities come first in schedule order. Order the presented options by delay, then cost.

There is no single "right" choice where several options remain. The Cost agent should naturally prefer the cheapest, the Time agent should prefer holding the date, and the Commercial agent should weigh contingency against buffer. The person decides.

---

## 3. Non-goals

- No real Aldar data, no integration with Oracle Primavera Unifier, Primavera P6, Pulse or any Aldar system.
- No parsing of real P6 XER files or drawings. The schedule is a simplified JSON export; changes are given as parameters (and, for the wall, drawing revision key data).
- No free-text change input in Phases 0 to 6 (optional in Phase 7).
- No login, roles, deployment or multi-user support. Runs locally.
- No Aldar logo. The UI is inspired by Aldar's brand guidelines (colours and typography) but carries only text: "Proof of concept by Sekuen, prepared for Aldar. Illustrative data."

---

## 4. Architecture

```
+---------------------------- Frontend (React) -----------------------------+
| Change selector | Evidence | Agent Room (graph + timeline) | Cost/Gantt/... |
|            Decision panel (approve) | Outputs | Trace drawer               |
+-----------------------------------^---------------------------------------+
                                    | REST + Server-Sent Events
+-----------------------------------+---------------------------------------+
|                         Backend (FastAPI, Python)                          |
|  Orchestrator --> Agent runtime (7 agents) --> LLM client (OpenAI)         |
|        |                 |                                                 |
|        |                 +--> Tool registry --> Deterministic engines      |
|        |                              |          (change, quantities, BOQ, |
|        |                              |           cost, productivity, CPM, |
|        |                              |           options, buffer, claim,  |
|        |                              |           notice, contract search) |
|        |                              +--> Fact registry (every number)    |
|        +--> Blackboard (shared run state) --> Event bus --> Run store      |
|        +--> Approval gate --> Action executor --> runs/<id>/outputs/       |
+---------------------------------------------------------------------------+
```

- **Deterministic engines** are pure Python with no LLM imports, unit-tested against the golden values.
- **Tools** wrap engines, validate inputs and outputs with Pydantic, and register every number they return in the **fact registry** with a fact ID.
- **Agents** are LLM loops with a role, a goal, an allowed tool list and a strict message format.
- **Orchestrator** runs the stages, routes messages and questions between agents, runs the Verifier on every message, enforces the approval gate, and emits events.
- **Event bus** streams every event to the UI over Server-Sent Events (SSE) and writes it to `runs/<run_id>/events.jsonl`.
- **Replay** streams a stored run back with original timing, so the demo works without the API.

The run context (`change_type`, `parameters`, `mode`, overrides) is fixed at run start and passed to every tool, so agents never pass change parameters themselves.

---

## 5. Tech stack and repository layout

### 5.1 Stack

| Layer | Choice | Notes |
|---|---|---|
| Backend | Python 3.11+, FastAPI, Uvicorn, Pydantic v2 | |
| LLM | OpenAI official Python SDK (`openai`), Chat Completions with tool calling | Model from `OPENAI_MODEL`; must support tool calling. Optional cheaper model for Intake and Verifier via `OPENAI_MODEL_LIGHT` |
| Agent framework | **None.** Our own explicit orchestrator and agent loop | Do not use LangChain, LangGraph, CrewAI, AutoGen or similar. Owning the loop is part of the proof |
| Search | `rank-bm25` for BOQ and contract search, plus exact code match | Small corpus; no embeddings needed |
| Schedule engine | Own CPM implementation (forward and backward pass) | `networkx` allowed only for topological sort and cycle detection |
| Tests | `pytest` (backend), `vitest` (frontend) | |
| Frontend | React 18 + TypeScript + Vite + Tailwind CSS | |
| Agent graph | `@xyflow/react` (React Flow) | Custom nodes and animated edges |
| Animation | `framer-motion` | Message flights, typing, stance changes |
| Charts | `recharts` for bars and scatter; Gantt as a custom SVG component | |
| PDF | Browser print stylesheet for the PVR form, plus a backend HTML file | |
| Tooling | `Makefile`, `.env`, `uv` or `pip` + `venv`, `npm`, Git | |

### 5.2 Repository layout

```
pvr-agent-room/
  CLAUDE.md
  SPEC.md
  README_FIRST.md
  README.md
  Makefile
  .env.example
  .gitignore
  data/                      # given, do not edit
  tests_golden/golden.json   # given, do not edit
  backend/
    pyproject.toml
    pvr/
      __init__.py
      config.py              # env, paths, model names
      models.py              # Pydantic models for data, run context, tools, messages, events
      data_loader.py
      engines/
        change.py            # change_types, get_change_request, compare_drawing_revisions
        quantities.py        # quantify_change (one rule per change type)
        boq.py               # search_boq, get_boq_item
        cost.py              # price_change, compare_contractor_claim
        productivity.py      # added_duration
        cpm.py               # run_cpm, calendar dates
        options.py           # evaluate_option, search_options (Pareto)
        buffer.py            # check_buffer
        contract.py          # search_contract, get_clause, check_notice
      tools/
        registry.py          # tool definitions, JSON schemas, dispatch
        facts.py             # fact registry
      llm/
        client.py            # OpenAI wrapper, retries, token logging
        fake.py              # FakeLLM for tests
      agents/
        base.py              # agent runtime loop
        prompts/             # one .md system prompt per agent
        roster.py            # agent definitions: role, goal, tools, model
      orchestrator/
        context.py           # RunContext
        blackboard.py
        stages.py
        orchestrator.py
        verifier.py          # deterministic checks used by the Verifier agent
        approvals.py
        actions.py           # action executor, artifact writers
      events/
        bus.py
        store.py             # runs/<id>/events.jsonl, replay
      api/
        main.py              # FastAPI app, routes, SSE
      cli.py
    tests/
      test_engines.py
      test_tools.py
      test_verifier.py
      test_orchestrator_fake.py
      test_live.py           # marked live, needs OPENAI_API_KEY
  frontend/
    package.json
    src/
      theme/tokens.css
      api/                   # REST + SSE client, typed events
      state/                 # event-driven run store
      components/
        layout/Header.tsx
        change/ChangeSelector.tsx
        evidence/            # ChangeCard, DrawingDiff, BoqLines, Clauses
        room/                # AgentGraph, AgentNode, Timeline, MessageBubble, ToolCallRow
        panels/              # CostPanel, GanttPanel, BufferPanel, OptionsPanel
        decision/            # DecisionPanel, OptionCard, ApprovalModal
        outputs/             # OutputsPanel, PvrFormPreview
        trace/TraceDrawer.tsx
        whatif/WhatIfControls.tsx
      App.tsx
  runs/                      # generated, git-ignored
  fixtures/                  # recorded demo runs for replay (committed)
```

---

## 6. Data

All files are in `data/`. All content is fictional.

| File | Content |
|---|---|
| `project.json` | Project, contract, calendar (Mon to Sat working, Sunday off, no holidays), data date, contract completion (working day 87), Employer commitment (working day 107), time buffer (20 wd), remaining cost contingency (AED 65,000) |
| `boq.json` | 38 BOQ lines in 6 bills: code, description, unit, quantity, rate, amount, lump-sum flag |
| `schedule.json` | 27 activities: id, name, WBS, zone, discipline, baseline duration, predecessors (FS or SS with lag), linked BOQ codes, status |
| `productivity.json` | Productivity per crew-day for roads, boundary wall and hardscape items, mapped to activities, plus the added-duration rule |
| `commercial.json` | Time-related cost per day, additional crew rates and limits, eligible activities per change type |
| `contract.json` | 11 contract clauses with full text (some relevant, some distractors) |
| `documents.json` | Element geometry for the road and hardscape; drawing register (L-201 Rev B and Rev C for the wall); variation instruction VI-017; contractor PVR-023 with claimed lines |
| `scenario.json` | The three change types: parameters with defaults and ranges, instruction text templates, allowed modes |

Day numbering convention (used everywhere): working days are integers from 0. An activity with early start ES and duration d occupies working days ES to ES+d-1 and has early finish EF = ES + d. The completion date of a finish EF is the calendar date of working day EF - 1. Working day 0 is Mon 26 Oct 2026. Delay = max(0, completion - 87). An over-accelerated option may finish before day 87; show its real completion date.

---

## 7. Deterministic engines

Pure functions. No LLM imports. Each returns a Pydantic model. Quantities and money rounded to 2 decimals at output. Ceilings use a small tolerance (round to 6 decimals before `ceil`).

### 7.1 Change engine (`change.py`)
- `list_change_types()`: from `scenario.json`.
- `get_change_request(ctx)`: returns a structured change request: id (`CR-<type>-<n>`), change type, parameters, mode, instruction text (template filled with parameters), and for the wall default in `contractor_pvr` mode the instruction VI-017 and contractor PVR-023.
- `compare_drawing_revisions(ctx)`: wall only: key parameter changes between L-201 Rev B and the requested height (Rev C at 2.5 m). For other change types return the element geometry and the parameter change.
- Validate parameters against ranges; reject invalid values with a clear error.

### 7.2 `quantify_change(ctx)` (one rule per change type)

**Wall (`wall_height`)**, from L-201 Rev B key data (length 400 m, spacing 4 m, columns 0.2 x 0.2 m, 2 faces) at old and new height H:
- B-04-010 blockwork = length x H
- B-04-015 stiffener columns = (floor(length / spacing) + 1) x 0.2 x 0.2 x H
- B-04-020 plaster = length x H x faces
- B-04-040 paint = length x H x faces
- B-04-030 coping = length (unchanged)
- Needs review: B-04-005, B-04-008 (footing designed for previous height; structural check needed)

**Road (`road_widening`)**, area = widen_by x length:
- R-02-010 excavation = area x 0.8 m depth
- R-02-020, R-02-030, R-02-040, R-02-060, R-02-070 = area each
- R-02-080 road markings = 0 (unchanged)
- Needs review: R-02-050 kerbs (kerb line moves; no BOQ rate for removal and re-laying; new rate needed under clause 13.3)

**Paving (`paving_area`)**:
- L-05-050 interlocking paving = added area
- L-05-060 granite paving = 0 (unchanged)

Return per code: old (where defined), new, delta; plus `unaffected` and `requires_review` lists with reasons.

### 7.3 `search_boq(query, top_k=5)` and `get_boq_item(code)`
BM25 over code + bill name + description, with exact code match ranked first. Return code, description, unit, quantity, rate, score.

### 7.4 `price_change(ctx)`
Uses the quantity deltas from `quantify_change`. Cost per line = delta x contract rate. Returns lines, rate source ("BOQ rate, clause 13.3"), total, and the items needing a new rate (priced at 0 and flagged, never guessed).

### 7.5 `added_duration(ctx)`
For each activity: ceiling(sum over its changed items of delta / productivity). Returns baseline duration, added days and new duration per affected activity.

### 7.6 `run_cpm(duration_overrides)`
Forward and backward pass over FS and SS relationships with lags. Returns completion working day and date, critical path (total float 0, in schedule order), and ES, EF, LS, LF, TF per activity. Detects cycles. Baseline: completion 87; wall chain TF 6; A420 TF 14; road chain on the critical path.

### 7.7 `evaluate_option(ctx, extra_crews_on)`
Start from the change's new durations. For each listed activity: new duration = ceiling(duration / 2); acceleration cost += 3,000 + 1,800 x accelerated duration. Run CPM. Delay = max(0, completion - 87). Time-related cost = 2,500 x delay. Total = direct cost + acceleration + time-related. Returns option ID, completion day and date, delay, cost parts, total, time buffer remaining, contingency remaining. Reject activities not eligible for the change type (`commercial.json`) and more than one extra crew per activity. Option ID: `OPT-NONE`, or `OPT-` plus activity IDs in schedule order joined by `-`.

### 7.8 `search_options(ctx)`
Evaluate every combination of eligible activities (8 for wall and road, 2 for paving). Return all options and the Pareto set with the rule in section 2.4.

### 7.9 `check_buffer(ctx, option_id)`
Returns time buffer remaining, contingency remaining, `within_time_buffer`, `within_contingency`, `budget_uplift_needed_aed` (0 if none), `exceeds_employer_commitment` (true if the buffer goes negative).

### 7.10 `compare_contractor_claim(ctx)`
Only in `contractor_pvr` mode. Line-by-line: claimed rate versus BOQ rate, claimed quantity versus assessed quantity, disallowed preliminaries, claimed versus assessed extension (OPT-NONE delay). Each adjustment carries its clause reference.

### 7.11 Contract (`contract.py`)
`search_contract(query, top_k=3)` (BM25 over title and text), `get_clause(clause_id)`, `check_notice(event_date, notice_date, limit_days=28)` (calendar days).

---

## 8. Tool layer

### 8.1 Tool registry
Each engine function is exposed as a tool with a name, a model-facing description, a JSON schema generated from Pydantic, and a dispatcher. The run context is injected by the dispatcher; agents only pass the arguments that are genuinely theirs to choose (search queries, option crews, clause IDs). Each agent sees only its allowed tools (section 9).

Orchestration tools:

| Tool | Purpose |
|---|---|
| `post_message(to, intent, content, claims, stance, proposals)` | The only way an agent ends its turn. `to` is an agent name or `all`. `intent`: ASSESS, PROPOSE, CHALLENGE, AGREE, ASK, ANSWER, VERIFY, SUMMARISE. `claims`: list of `{label, value, unit, fact_id}`. `stance`: preferred option ID or null. `proposals`: option IDs |
| `ask_agent(to, question)` | Directed question to another agent. The orchestrator runs a short answer turn for the target agent and returns its answer as the tool result. Depth 1, at most 2 asks per turn |
| `propose_action(type, payload, reason)` | Queue an action for approval: `create_task`, `draft_pvr_form`, `draft_verification_report`, `notify` |
| `read_blackboard(section)` | Read shared state written by earlier stages |

### 8.2 Fact registry
Every numeric value in every tool result is registered as a fact: `{fact_id, tool_call_id, tool, path, value, unit}` (for example `F-0007`, path `total_aed`). Tool results returned to the model show fact IDs next to values, so the model can cite them. The UI can open any fact and show the tool call that produced it.

---

## 9. Agents

Seven agents, each with a system prompt in `agents/prompts/`. Prompts state the role, goal, allowed tools, the core rule (section 1.2), the message format, and that every number must cite a fact ID and every contract statement a clause ID. Prompts are generic across change types: no change-specific instructions.

| Agent | Role and goal | Allowed tools |
|---|---|---|
| **Intake** | Understand the change and package the evidence | get_change_request, compare_drawing_revisions, check_notice, post_message |
| **Contract** | Determine eligibility and the contract rules that apply; raise design and new-rate issues | search_contract, get_clause, read_blackboard, propose_action, post_message |
| **Cost** (quantity surveyor) | Quantify and price the change; argue for value for money | quantify_change, search_boq, get_boq_item, price_change, compare_contractor_claim, check_buffer, ask_agent, read_blackboard, post_message |
| **Time** (planner) | Assess the programme impact; argue for protecting the completion date | added_duration, run_cpm, evaluate_option, ask_agent, read_blackboard, post_message |
| **Commercial** | Weigh contingency and time buffer; find the full option set | search_options, evaluate_option, check_buffer, ask_agent, read_blackboard, post_message |
| **Verifier** | Check every claim in every message | deterministic checks (section 10.4) plus post_message |
| **Moderator** | Run the debate, synthesise options, prepare the decision | read_blackboard, search_options, propose_action, post_message |

Expected behaviour (used to judge prompts, never put into prompts):

| Change | Intake | Contract | Cost | Time | Commercial |
|---|---|---|---|---|---|
| Wall 2.5 m, contractor PVR | Height change B to C, VI-017 and PVR-023, notice within 28 days | Eligible (13.1), BOQ rates (13.3), no preliminaries % (13.4), extension only on the critical path (8.4), time-related costs (8.5), acceleration rates (8.6); proposes a structural check task (4.1) | 4 items, coping unaffected, AED 43,529; challenges contractor rates and preliminaries | 14 days gross, 6 float, 8 delay; argues for OPT-A320 | Points out OPT-A320 breaks contingency by 4,929 and OPT-A340 keeps both |
| Road 1.0 m x 600 m | Widening and length | New rate needed for kerb relocation (13.3); extension on critical path (8.4) | 6 items, markings unaffected, kerbs need a new rate, AED 100,440 | Critical path, 5 days delay; OPT-A120 holds the date for only 1,300 more | All options need a budget uplift; recommends deciding on time value |
| Paving 400 m2 | Added area | Eligible variation at BOQ rates | 1 item, granite unaffected, AED 36,800 | 2 days absorbed by float, no delay | Within contingency; no acceleration needed. Quick agreement |

Moderator: presents up to 3 options from evaluated option IDs only, with each agent's final stance; proposes `draft_pvr_form`, `draft_verification_report` (contractor PVR mode only) and `notify` actions.

Agent loop (`agents/base.py`): build messages (system prompt, stage instruction, relevant blackboard sections, messages addressed to this agent), call the model with the allowed tools, execute tool calls, append results, repeat until the agent calls `post_message` or hits the step limit (default 8). On the limit, the orchestrator asks once for `post_message`, then marks the turn failed.

---

## 10. Orchestration protocol

### 10.1 Message envelope

```json
{
  "message_id": "M-0012",
  "run_id": "R-...",
  "stage": "debate",
  "round": 2,
  "from": "time",
  "to": "cost",
  "intent": "CHALLENGE",
  "content": "Accepting the delay uses 40% of the buffer for one change...",
  "claims": [{"label": "delay", "value": 8, "unit": "wd", "fact_id": "F-0031"}],
  "stance": "OPT-A320",
  "proposals": ["OPT-A320"],
  "verification": {"status": "pass", "issues": []},
  "timestamp": "..."
}
```

### 10.2 Stages

| Stage | Who | What happens |
|---|---|---|
| 1. Intake | Intake | Change summary and evidence written to the blackboard |
| 2. Assessment | Contract, Cost, Time (concurrent) | Each posts ASSESS. Cost and Time may `ask_agent` each other or Contract |
| 3. Commercial check | Commercial | Full option search and buffer check, posts ASSESS |
| 4. Debate | Cost, Time, Commercial; Contract can answer | Up to 3 rounds. Each debater posts PROPOSE, CHALLENGE or AGREE to a specific agent, with a stance. Stop early when stances have not changed for a full round, or immediately after round 1 if the Pareto set has a single option |
| 5. Synthesis | Moderator | SUMMARISE with up to 3 options, trade-offs, stances, proposed actions |
| 6. Approval | Person (UI) | Choose one option, tick actions, enter name and role, approve or reject |
| 7. Action | Action executor | Executes approved actions and writes artifacts |

After every agent message, the Verifier runs (section 10.4). In `internal_what_if` mode, skip `compare_contractor_claim` and the verification report.

### 10.3 Blackboard sections
`change`, `quantities`, `cost`, `schedule_impact`, `contract_findings`, `options`, `buffer`, `claim_comparison`, `stances` (per agent per round), `pending_actions`, `decision`, `executed_actions`.

### 10.4 Verification
Deterministic checks first, then a short Verifier message explaining the result:

1. Every claim has a `fact_id` that exists in the fact registry, the value matches within 0.01, and the unit matches.
2. Every number in `content` is covered by a claim (regex extraction; ignore option IDs, clause IDs, BOQ codes, activity IDs, and dates or percentages already covered by claims).
3. Every clause referenced exists in `contract.json`.
4. Every option ID referenced was evaluated in this run.

On failure: the message is marked `fail` with issues, and the author gets one correction turn. The corrected message replaces it in the timeline, with the original visible but struck through. A second failure is shown as unresolved.

### 10.5 Approval gate and actions
- Proposed actions are stored as `pending` with author and reason.
- `POST /api/runs/{id}/approve` with the chosen option, approved action IDs, approver name and role.
- The executor then writes, under `runs/<id>/outputs/`: `pvr_output_form.json` and `.html` (change, quantities, cost, schedule impact, chosen option, clauses, approver); `verification_report.json` and `.html` (contractor PVR mode only); `tasks.json` (for example a structural check, or a new rate for kerb relocation); `notifications.json` (planner, quantity surveyor, contracts).
- Executing before approval raises an error and emits `run.error`. A test proves this.

---

## 11. API and events

### 11.1 REST

| Method and path | Purpose |
|---|---|
| `GET /api/health` | Health check |
| `GET /api/change-types` | Change types with parameters, defaults, ranges and modes |
| `GET /api/data/{name}` | Data files for the evidence panel |
| `POST /api/runs` | Start a run: `{change_type, parameters, mode, overrides?}`. Overrides: `cost_contingency_remaining_aed`, `time_buffer_working_days` |
| `GET /api/runs/{id}/events` | SSE stream of live events |
| `GET /api/runs/{id}` | Run state snapshot |
| `POST /api/runs/{id}/approve` | Approval (section 10.5) |
| `POST /api/runs/{id}/reject` | Reject with reason |
| `GET /api/runs/{id}/outputs/{file}` | Download artifacts |
| `GET /api/runs` | List stored runs |
| `GET /api/replay/{id}?speed=1.0` | SSE replay of a stored run or fixture |

### 11.2 Event types
`run.started`, `stage.started`, `stage.completed`, `agent.active`, `agent.idle`, `tool.called`, `tool.result`, `fact.registered`, `ask.sent`, `ask.answered`, `message.posted`, `verification.result`, `message.corrected`, `stance.changed`, `option.evaluated`, `options.final`, `action.proposed`, `approval.requested`, `approval.granted`, `approval.rejected`, `action.executed`, `run.completed`, `run.error`.

Each event: `{event_id, run_id, type, ts, payload}`. The frontend renders entirely from events, so live and replay share one code path.

---

## 12. Frontend

### 12.1 Theme (inspired by Aldar's brand guidelines)

Use the Blues accent set only (the guidelines say not to mix accent sets). Typeface Poppins (Google Fonts). No Aldar logo.

```css
:root {
  --bg: #FFFFFF;               /* Aldar White */
  --surface: #F7F6F4;          /* light tint of Warm Grey */
  --surface-2: #EFECE8;
  --border: #D7D2CB;           /* Warm Grey */
  --text: #2C2A29;             /* Aldar Black */
  --text-muted: #6E6A66;
  --accent: #003057;           /* Night Shade */
  --accent-2: #69B3E7;         /* Sky */
  --accent-tint: #E6F1FA;      /* light Sky tint for highlights */
  --alert: #E35205;            /* Terracotta: only failed verification, budget overrun, buffer breach */
  --radius: 10px;
  --font: "Poppins", system-ui, sans-serif;
}
```

Style: calm, generous white space, thin warm-grey borders, Night Shade for headings and key numbers, Sky for live activity and highlights. Headings Poppins 600, numbers 700, body 400. Desktop first (1440 px), usable at 1280 px.

Agent identity (icon + label + colour; never colour alone):

| Agent | Colour | Icon idea |
|---|---|---|
| Moderator | #003057 | table or gavel |
| Intake | #69B3E7 | inbox |
| Contract | #2C2A29 | document with seal |
| Cost | #1F5C8B | calculator |
| Time | #4A9BD4 | clock |
| Commercial | #8A847E | scale |
| Verifier | #3D3A38, outline style | shield with a check |

### 12.2 Layout

| Area | Content |
|---|---|
| Start screen: Change selector | Three cards (wall, road, paving) with a one-line description each. Selecting a card shows its parameter inputs (sliders with number fields, ranges from the API), the mode toggle where allowed (wall at 2.5 m: contractor PVR or internal what-if), the generated instruction text, and **Run agents**. Also: Replay a saved run |
| Header (during a run) | Title "PVR Agent Room"; subtitle "Proof of concept by Sekuen, prepared for Aldar. Illustrative data."; current change and parameters; New change; speed control (0.5x, 1x, 2x); 7-stage progress bar |
| Left column (about 25%) | Change card (instruction, and PVR-023 in contractor mode); parameter or drawing revision diff; affected BOQ lines filled in as agents find them, with unaffected items greyed and review items flagged; cited clauses as chips (click shows the clause text) |
| Centre (about 45%) | **Agent Room graph** on top: 7 agent nodes around the Moderator. Active agent pulses; tool calls appear as small sparks on the node; messages and `ask_agent` calls fly along animated edges; stance badge under each node. **Timeline** below: chat-style bubbles labelled by agent and intent; claim chips open the source fact; Verifier tick or alert per bubble; tool calls as collapsible rows ("Time called run_cpm: completion day 95"); corrected messages show the struck-through original |
| Right column (about 30%), tabs | **Cost**: line breakdown; in contractor mode, claimed versus assessed. **Schedule**: custom SVG Gantt of the critical path and the affected chain, baseline versus impacted bars, float shading, completion and commitment markers. **Buffer**: gauges for time buffer and contingency per option. **Options**: scatter of cost versus delay for all options, Pareto points highlighted |
| Decision panel (stage 6) | Up to 3 option cards (crews, delay, completion date, cost, buffer and contingency left, supporting agents), action checklist, approver name and role, Approve and Reject |
| Outputs | After approval: PVR output form preview (print to PDF), verification report, tasks, notifications |
| Trace drawer (Phase 6) | Full event log with filters, model, tokens, latency per call; download trace |
| What-if controls (Phase 6) | Change parameters, contingency and time buffer; "Re-run agents" |

### 12.3 Interaction details
- The UI never computes business numbers; it only displays values from events.
- Typing effect for message content (fast, skippable).
- Clicking an agent node filters the timeline to that agent and shows its stance history.
- Clicking a claim chip highlights the fact and its tool call.
- Empty, loading and error states for every panel.

---

## 13. Configuration

`.env` (never committed):

```
OPENAI_API_KEY=...
OPENAI_MODEL=<a tool-calling model you have access to>
OPENAI_MODEL_LIGHT=<optional cheaper model for Intake and Verifier>
LLM_TEMPERATURE=0.4
MAX_DEBATE_ROUNDS=3
AGENT_MAX_STEPS=8
```

LLM client: timeouts, 2 retries with backoff, token and latency logging per call into the trace.

---

## 14. Testing

| Test file | What it proves |
|---|---|
| `test_engines.py` | Every value in `golden.json` for every case: quantity deltas, unaffected and review items, direct cost, added durations, all options, Pareto IDs and order, buffer and contingency, baseline ES/EF/TF, contractor claim comparison, notice check. Parameter validation rejects out-of-range values |
| `test_tools.py` | Schemas, run context injection, input validation, fact registration (every number in a tool result has a fact ID) |
| `test_verifier.py` | Correct claim passes; wrong value fails; missing fact fails; bare number without a claim fails; unknown clause fails; unevaluated option fails |
| `test_orchestrator_fake.py` | With FakeLLM scripted responses: full stage flow; asks routed; correction turn on a failed verification; early debate stop with a single Pareto option; no action before approval; artifacts after approval |
| `test_live.py` (marked `live`) | Real model, all three defaults: final options equal the golden Pareto set; all final messages verified; wall and road runs have at least one `ask_agent`, at least 2 debate rounds and at least one CHALLENGE; paving run ends the debate early; no action before approval |

Frontend: `vitest` for the event reducer and number formatting.

---

## 15. Run commands

```
make setup         # backend venv + deps, frontend npm install
make dev           # backend on :8000, frontend on :5173
make test          # pytest (excluding live) + vitest
make test-live     # live tests with OPENAI_API_KEY
make cli-engines   # deterministic report for all three defaults, no LLM
make cli-run CHANGE=wall_height   # full agent run in the console with an approval prompt
```

---

## 16. Phases and checkpoints

### 16.0 Checkpoint protocol (every phase)
1. Implement only the requested phase.
2. Run `make test` (and the phase's CLI or live check where listed) and fix failures.
3. Report: each checkpoint item as done or not done, files created or changed, anything skipped, assumed or questionable.
4. When all checkpoint items pass, **ask the user**: "Checkpoint N reached, all tests pass. Shall I commit?" Do not commit until the user says yes.
5. On yes: `git add -A` then `git commit -m "Checkpoint N: <phase name>"`. Check that `.env` is not staged. Never push unless the user explicitly asks.
6. Stop and wait for the next instruction.

### Phase 0: Scaffold
- Repository layout, `Makefile`, `.env.example`, `.gitignore` (`.env`, `runs/`, `node_modules/`, `.venv/`, build output), README with run steps.
- Backend FastAPI app with `/api/health`. Frontend Vite app with theme tokens, Poppins, header and empty layout.
- Do not copy the data: the backend reads `data/` and `tests_golden/` from the repository root.

**Checkpoint 0:** `make setup` and `make dev` work; `/api/health` returns ok; the browser shows the themed header and empty layout; `make test` passes.

### Phase 1: Data and deterministic engines
- Pydantic models and loaders for all data files; RunContext.
- All engines in section 7 for all three change types, with docstrings.
- `cli.py engines` prints a readable deterministic assessment for each default case.

**Checkpoint 1:** every golden test passes for all six cases; no LLM import under `engines/`; CLI output matches section 2.4.

### Phase 2: Tools, facts, LLM client, single agent
- Tool registry with JSON schemas, context injection, dispatch and fact registration.
- LLM client (OpenAI) and FakeLLM. Agent runtime loop and `post_message`.
- Cost agent prompt; `cli.py agent cost --change wall_height` runs it alone with earlier blackboard sections pre-filled from engines.

**Checkpoint 2:** the Cost agent, live, finds the affected items, states the direct cost with fact IDs and names the unaffected and review items, for the wall and the road; the trace file is written; FakeLLM test passes.

### Phase 3: Multi-agent orchestration
- All 7 agents and prompts, blackboard, stages, `ask_agent`, debate rounds with stance tracking and early stop, Verifier with correction turn, Moderator synthesis, approval gate, action executor and artifacts.
- `cli.py run --change <type>` runs everything in the console, pauses for approval, then executes actions.

**Checkpoint 3:** live runs complete for all three defaults; final options equal the golden Pareto sets; behaviour matches section 14 `test_live.py`; verifier and approval tests pass; artifacts exist only after approval.

### Phase 4: API, streaming, run store, replay
- Endpoints in section 11.1, SSE events in section 11.2, `runs/<id>/events.jsonl`, replay with speed control.
- Save one good live run per change type as `fixtures/demo_run_<change_type>.jsonl`.

**Checkpoint 4:** a live run can be watched with `curl -N`; approval through the API works; replay of each fixture works with no API key set.

### Phase 5: Frontend core
- Change selector and all components in section 12 except What-if and Trace drawer.
- Event-driven state store used for live and replay.

**Checkpoint 5:** from the change selector, a full live run plays for each change type, from Run to approved outputs; replays play identically; the Agent Room shows agents, flying messages and asks, tool sparks and stances; every number shown comes from events; style matches section 12.1.

### Phase 6: Proof features and polish
- What-if controls and re-run; Trace drawer; claim-chip to fact linking; print-to-PDF for the PVR form; loading and error states; demo script in README.
- Optional, clearly labelled "stress test" toggle that tells the Cost agent to use the contractor's rates in its first draft (wall contractor mode), so the audience sees the Verifier catch and correct it.

**Checkpoint 6:** wall 3.0 m shows the buffer breach for OPT-NONE and different options; contingency 75,000 makes OPT-A320 fit the budget for the wall; the rehearsal checklist (section 17) passes end to end.

### Phase 7 (optional): extras
- Free-text change input: the Intake agent maps a typed request to one of the three change types and parameters, shows its interpretation, and the user confirms before the run continues. Requests outside the three types are politely declined.
- Agent-to-agent style endpoints with agent cards, routing `ask_agent` over HTTP (aligns with our A2A-T work).
- Arabic and English UI toggle with right-to-left layout.

---

## 17. Demo script and rehearsal checklist

1. Open the app. Show the contract clauses and the BOQ in the evidence panel. Say: "Choose a change, and set its size."
2. Let Aldar pick. Start with the wall (2.5 m, contractor PVR mode) if they have no preference.
3. Point at Intake, then Contract, Cost and Time working in parallel, and an agent asking another a question.
4. Schedule tab: added days versus float, and the resulting delay.
5. Debate: challenges and stance badges changing; Commercial running the full option search.
6. A Verifier tick, and if using the stress test, a caught error and its correction.
7. Decision panel: options and each agent's stance. Approve one as a named person.
8. Outputs: PVR form, verification report (contractor mode), tasks, notifications.
9. Run a second change (road or paving) to show different behaviour from the same agents.
10. Open the Trace drawer: every tool call, fact and message, replayable.

Rehearsal checklist: each live run under 4 minutes; replays work offline; no console errors; every number on screen traceable to a fact; nothing executed before approval.

---

## 18. Guardrails for the build

- Keep engines pure and tested; never put expected numbers inside engine code.
- Agents never receive golden values; prompts are generic across change types.
- Prompts describe roles and goals, never a fixed sequence of tool calls.
- Log every LLM call (model, tokens, latency) to the trace.
- No secrets in code, logs or commits. `.env` is git-ignored.
- Clear, simple English in all UI text; spell out abbreviations once (for example "PVR (potential variation request)").
