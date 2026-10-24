"""Agent runtime with FakeLLM: tool loop, post_message, step limit, nudges and the trace file."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from conftest import fake_settings, make_session
from pvr.agents.base import run_agent_turn, system_prompt
from pvr.agents.roster import COST
from pvr.data_loader import get_data
from pvr.engines.change import make_context
from pvr.events.store import read_events
from pvr.llm.fake import FakeLLM, text, tool_call, tool_calls
from pvr.orchestrator.context import RunSession
from pvr.orchestrator.single_agent import intake_section, run_single_agent
from pvr.orchestrator.stages import stage_instruction
from pvr.tools.registry import REGISTRY

ASSESS = stage_instruction("assessment")


def post_citing(session_ref: dict[str, RunSession]) -> Any:
    """A scripted step that cites the direct cost fact the price_change call registered."""

    def step(messages: list[dict[str, Any]]) -> Any:
        session = session_ref["session"]
        fact = session.facts.find("price_change", "direct_cost_aed")[-1]
        return tool_call("post_message", {
            "to": "all", "intent": "ASSESS",
            "content": f"Direct cost is AED {fact.value} at BOQ rates (clause 13.3).",
            "claims": [{"label": "direct cost", "value": fact.value, "unit": "AED", "fact_id": fact.fact_id}],
            "stance": None,
        })

    return step


def test_cost_turn_with_tools_and_post_message() -> None:
    session = make_session("wall_height")
    session.blackboard.write("change", intake_section(session), "test")
    ref = {"session": session}
    llm = FakeLLM([
        tool_calls([("quantify_change", {}), ("price_change", {})]),
        post_citing(ref),
    ])
    turn = run_agent_turn(session, COST, llm, ASSESS, blackboard_sections=["change"])

    assert turn.status == "posted" and not turn.forced and turn.steps == 2
    message = turn.message
    assert message is not None and message.intent == "ASSESS" and message.from_agent == "cost"
    claim = message.claims[0]
    assert session.facts.check_claim(claim.fact_id, claim.value, claim.unit) is None
    assert claim.value == session.facts.get(claim.fact_id).value  # type: ignore[union-attr]

    # Tool results went back to the model with fact ids; the agent saw only its own tools.
    second = llm.requests[1]
    tool_msgs = [m for m in second.messages if m["role"] == "tool"]
    assert len(tool_msgs) == 2 and "[F-" in tool_msgs[1]["content"]
    assert "search_options" not in second.tool_names and "post_message" in second.tool_names
    assert "compare_contractor_claim" not in second.tool_names  # what-if mode
    # Blackboard content came in through read_blackboard, so its numbers have fact ids too.
    assert "[F-" in second.messages[1]["content"]

    types = [e.type for e in session.bus.events]
    for expected in ("agent.active", "llm.call", "tool.called", "tool.result", "fact.registered",
                     "message.posted", "agent.idle"):
        assert expected in types
    assert session.bus.of_type("llm.call")[0].payload["prompt_tokens"] == 100


def test_plain_text_reply_is_nudged_to_post() -> None:
    session = make_session("paving_area")
    llm = FakeLLM([
        text("I think the cost is fine."),
        tool_call("post_message", {"to": "all", "intent": "ASSESS", "content": "No numbers yet."}),
    ])
    turn = run_agent_turn(session, COST, llm, ASSESS)
    assert turn.status == "posted" and turn.steps == 2
    assert llm.requests[1].messages[-1] == {"role": "user", "content": "Please end your turn by calling post_message."}


def test_invalid_post_message_is_returned_as_error_and_retried() -> None:
    session = make_session("paving_area")
    llm = FakeLLM([
        tool_call("post_message", {"to": "nobody", "intent": "ASSESS", "content": "x"}),
        tool_call("post_message", {"to": "all", "intent": "ASSESS", "content": "Fixed recipient."}),
    ])
    turn = run_agent_turn(session, COST, llm, ASSESS)
    assert turn.status == "posted" and turn.steps == 2
    error_msg = [m for m in llm.requests[1].messages if m["role"] == "tool"][-1]["content"]
    assert "'to' must be one of" in error_msg


def test_disallowed_tool_is_refused_and_loop_continues() -> None:
    session = make_session("road_widening")
    llm = FakeLLM([
        tool_call("search_options"),
        tool_call("post_message", {"to": "all", "intent": "ASSESS", "content": "Done."}),
    ])
    turn = run_agent_turn(session, COST, llm, ASSESS)
    assert turn.status == "posted"
    refused = session.bus.of_type("tool.result")[0].payload
    assert refused["tool"] == "search_options" and not refused["ok"]


def test_step_limit_asks_once_then_fails() -> None:
    session = make_session("paving_area")
    llm = FakeLLM([tool_call("quantify_change")] * 3 + [text("still thinking")])
    turn = run_agent_turn(session, COST, llm, ASSESS, max_steps=3)
    assert turn.status == "failed" and turn.steps == 4
    forced = llm.requests[-1]
    assert forced.tool_choice == {"type": "function", "function": {"name": "post_message"}}
    assert "step limit" in forced.messages[-1]["content"]
    assert session.bus.of_type("agent.idle")[-1].payload["status"] == "failed"


def test_step_limit_reminder_can_succeed() -> None:
    session = make_session("paving_area")
    llm = FakeLLM([tool_call("price_change")] * 2
                  + [tool_call("post_message", {"to": "all", "intent": "ASSESS", "content": "Late."})])
    turn = run_agent_turn(session, COST, llm, ASSESS, max_steps=2)
    assert turn.status == "posted" and turn.forced


def test_prompt_is_generic_and_lists_allowed_tools() -> None:
    session = make_session("wall_height", mode="contractor_pvr")
    tools = REGISTRY.available_for(session, list(COST.tools))
    prompt = system_prompt(COST, tools)
    for name in [t.name for t in tools]:
        assert f"`{name}`" in prompt
    assert "{tools}" not in prompt
    golden = json.loads((Path(__file__).parents[2] / "tests_golden" / "golden.json").read_text(encoding="utf-8"))
    banned = {str(c["direct_cost_aed"]).removesuffix(".0") for c in golden["cases"]}
    banned |= {"B-04-010", "R-02-010", "L-05-050", "wall", "road", "paving", "OPT-A320", "OPT-NONE"}
    for text_ in banned:
        assert text_ not in prompt, text_


def test_single_agent_run_writes_trace(tmp_path: Path) -> None:
    data = get_data()
    ctx = make_context(data, "road_widening")
    llm = FakeLLM([tool_call("price_change"), tool_call("post_message", {"to": "all", "intent": "ASSESS", "content": "Priced."})])
    session, turn = run_single_agent("cost", ctx, data, fake_settings(), llm, runs_dir=tmp_path)
    assert turn.status == "posted"
    trace = tmp_path / session.run_id / "events.jsonl"
    events = read_events(trace)
    assert [e.type for e in events][0] == "run.started" and events[-1].type == "run.completed"
    assert len(events) == len(session.bus.events)
    assert all(e.run_id == session.run_id for e in events)
    assert session.blackboard.read("change") is not None
    assert "sk-" not in trace.read_text(encoding="utf-8")
