"""Live tests with the real model (marked `live`; run with scripts\\test.ps1 -Live).

Phase 2: the Cost agent alone, for the wall and the road.
Phase 3: full runs for the three defaults (SPEC 14, test_live.py).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pvr.config import GOLDEN_PATH, load_settings
from pvr.data_loader import get_data
from pvr.engines import cost, quantities
from pvr.engines.change import make_context
from pvr.events.store import read_events
from pvr.llm.client import OpenAILLM
from pvr.orchestrator.orchestrator import start_run
from pvr.orchestrator.single_agent import run_single_agent

pytestmark = pytest.mark.live

SETTINGS = load_settings()
needs_key = pytest.mark.skipif(not (SETTINGS.has_api_key and SETTINGS.openai_model),
                               reason="OPENAI_API_KEY and OPENAI_MODEL are needed")


@needs_key
@pytest.mark.parametrize("change_type", ["wall_height", "road_widening"])
def test_cost_agent_live(change_type: str, tmp_path: Path) -> None:
    data = get_data()
    ctx = make_context(data, change_type, mode=data.change_type(change_type).modes[0])
    session, turn = run_single_agent("cost", ctx, data, SETTINGS, OpenAILLM(SETTINGS), runs_dir=tmp_path)

    assert turn.status == "posted", turn.error
    message = turn.message
    assert message is not None and message.from_agent == "cost"

    # Every claim cites an existing fact with a matching value and unit.
    problems = [session.facts.check_claim(c.fact_id, c.value, c.unit) for c in message.claims]
    assert not [p for p in problems if p], problems

    # The direct cost is stated with a fact id from price_change.
    direct = cost.price_change(ctx, data).direct_cost_aed
    cited = [session.facts.get(c.fact_id) for c in message.claims]
    assert any(f and f.tool == "price_change" and f.path == "direct_cost_aed" and f.value == direct for f in cited)

    # Affected, unaffected and review items are all named.
    q = quantities.quantify_change(ctx, data)
    for code in [line.code for line in q.changed_lines()] + [u.code for u in q.unaffected] + \
            [r.code for r in q.requires_review]:
        assert code in message.content, code

    # The trace is written.
    events = read_events(tmp_path / session.run_id / "events.jsonl")
    assert any(e.type == "llm.call" for e in events) and events[-1].type == "run.completed"


# --- Phase 3: full runs ---------------------------------------------------------------------------

GOLDEN = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def golden_default_pareto(change_type: str) -> list[str]:
    data = get_data()
    defaults = {p.name: p.default for p in data.change_type(change_type).parameters}
    case = next(c for c in GOLDEN["cases"] if c["change_type"] == change_type and c["parameters"] == defaults)
    return case["pareto_option_ids"]


@needs_key
@pytest.mark.parametrize("change_type", ["wall_height", "road_widening", "paving_area"])
def test_full_run_live(change_type: str, tmp_path: Path) -> None:
    data = get_data()
    ctx = make_context(data, change_type, mode=data.change_type(change_type).modes[0])
    orch, sink = start_run(ctx, data, SETTINGS, OpenAILLM(SETTINGS), runs_dir=tmp_path)
    try:
        request = orch.run_until_approval()
        bus = orch.session.bus

        # Final options equal the golden Pareto set.
        assert request["options"] == golden_default_pareto(change_type)

        # All final messages verified.
        results = {e.payload["message_id"]: e.payload for e in bus.of_type("verification.result")}
        final = [m for m in orch.session.messages if m.superseded_by is None and m.intent not in ("ASK", "VERIFY")]
        unverified = [(m.message_id, m.from_agent, results.get(m.message_id, {}).get("issues")) for m in final
                      if m.verification.status != "pass"]
        assert not unverified, unverified

        # Nothing executed before approval.
        assert not bus.of_type("action.executed")
        outputs = orch.session.run_dir / "outputs"  # type: ignore[operator]
        assert not outputs.exists()

        debate_done = next(e.payload for e in bus.of_type("stage.completed") if e.payload["stage"] == "debate")
        debate = [m for m in orch.session.messages if m.stage == "debate"]
        if change_type == "paving_area":
            assert debate_done["rounds"] == 1 and debate_done["stop_reason"] == "single_pareto_option"
        else:
            assert bus.of_type("ask.sent"), "expected at least one ask_agent"
            assert debate_done["rounds"] >= 2
            assert any(m.intent == "CHALLENGE" for m in debate)

        # Approval executes the approved actions and only then writes artifacts.
        actions = [a["action_id"] for a in request["pending_actions"]]
        orch.approve(request["options"][0], actions, "Live Test", "Project Director")
        assert bus.of_type("action.executed") or not actions
        assert (outputs / "decision.json").exists()
    finally:
        sink.close()
