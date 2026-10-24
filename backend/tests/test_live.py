"""Live tests with the real model (marked `live`; run with scripts\\test.ps1 -Live).

Phase 2: the Cost agent alone, for the wall and the road. Phase 3 adds full runs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pvr.config import load_settings
from pvr.data_loader import get_data
from pvr.engines import cost, quantities
from pvr.engines.change import make_context
from pvr.events.store import read_events
from pvr.llm.client import OpenAILLM
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
