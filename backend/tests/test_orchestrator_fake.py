"""Orchestrator with FakeLLM: stage flow, asks, corrections, debate stop, approval gate, artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from conftest import fake_settings
from fake_room import Room, post
from pvr.config import GOLDEN_PATH
from pvr.data_loader import get_data
from pvr.engines.change import make_context
from pvr.llm.fake import tool_call
from pvr.orchestrator.approvals import ApprovalError
from pvr.orchestrator.context import TurnState, current_turn
from pvr.orchestrator.orchestrator import Orchestrator, start_run
from pvr.tools.registry import REGISTRY

GOLDEN = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def golden_pareto(change_type: str) -> list[str]:
    case = next(c for c in GOLDEN["cases"] if c["change_type"] == change_type)
    return case["pareto_option_ids"]


def new_run(tmp_path: Path, change_type: str, room: Room, scripts: dict[str, list[Any]] | None = None,
            mode: str = "internal_what_if", concurrent: bool = False) -> Orchestrator:
    data = get_data()
    ctx = make_context(data, change_type, mode=mode)  # type: ignore[arg-type]
    orch, _ = start_run(ctx, data, fake_settings(), room.llm(scripts), runs_dir=tmp_path, concurrent=concurrent)
    room.session = orch.session
    return orch


def types(orch: Orchestrator) -> list[str]:
    return [e.type for e in orch.session.bus.events]


def test_full_stage_flow_and_early_stop_with_single_option(tmp_path: Path) -> None:
    room = Room()
    orch = new_run(tmp_path, "paving_area", room, concurrent=True)
    request = orch.run_until_approval()

    stages = [e.payload["stage"] for e in orch.session.bus.of_type("stage.started")]
    assert stages == ["intake", "assessment", "commercial", "debate", "synthesis", "approval"]
    debate_done = next(e for e in orch.session.bus.of_type("stage.completed") if e.payload["stage"] == "debate")
    assert debate_done.payload == {"stage": "debate", "rounds": 1, "stop_reason": "single_pareto_option"}

    assert request["options"] == golden_pareto("paving_area")
    final = orch.session.bus.of_type("options.final")[0].payload
    assert [o["option_id"] for o in final["options"]] == golden_pareto("paving_area")
    assert {a["type"] for a in request["pending_actions"]} == {"draft_pvr_form", "notify"}
    assert orch.state == "awaiting_approval"
    # Every message posted by a debating or assessing agent was verified.
    results = {e.payload["message_id"]: e.payload["status"] for e in orch.session.bus.of_type("verification.result")}
    for m in orch.session.messages:
        if m.intent not in ("ASK", "VERIFY"):
            assert results.get(m.message_id) == "pass", m


def test_no_action_before_approval_then_artifacts_after(tmp_path: Path) -> None:
    room = Room()
    orch = new_run(tmp_path, "wall_height", room, mode="contractor_pvr")
    request = orch.run_until_approval()
    outputs = orch.session.run_dir / "outputs"  # type: ignore[operator]
    assert "action.executed" not in types(orch)
    assert not outputs.exists()

    with pytest.raises(ApprovalError):
        orch.execute()
    assert orch.session.bus.of_type("run.error")[-1].payload["error"] == "Execution attempted before approval"
    assert not outputs.exists()

    with pytest.raises(ApprovalError):
        orch.approve("OPT-A330", [], "Sam Lee", "Project Director")  # not presented
    with pytest.raises(ApprovalError):
        orch.approve(request["options"][0], [], " ", "Project Director")  # no name

    action_ids = [a["action_id"] for a in request["pending_actions"]]
    executed = orch.approve(request["options"][1], action_ids, "Sam Lee", "Project Director")
    assert {e.type for e in executed} == {"draft_pvr_form", "notify"}
    assert (outputs / "pvr_output_form.json").exists() and (outputs / "pvr_output_form.html").exists()
    assert (outputs / "notifications.json").exists() and (outputs / "decision.json").exists()
    form = json.loads((outputs / "pvr_output_form.json").read_text(encoding="utf-8"))
    assert form["chosen_option"]["option_id"] == request["options"][1]
    assert form["approver"]["name"] == "Sam Lee"
    # Every executed event comes after approval.granted.
    order = types(orch)
    assert order.index("approval.granted") < order.index("action.executed")
    assert order[-1] == "run.completed"


def test_reject_executes_nothing(tmp_path: Path) -> None:
    room = Room()
    orch = new_run(tmp_path, "paving_area", room)
    orch.run_until_approval()
    orch.reject("Sam Lee", "Project Director", "Not now")
    assert "action.executed" not in types(orch)
    assert not (orch.session.run_dir / "outputs").exists()  # type: ignore[operator]
    with pytest.raises(ApprovalError):
        orch.approve("OPT-NONE", [], "Sam Lee", "Project Director")


def test_debate_runs_two_rounds_and_stops_when_stances_hold(tmp_path: Path) -> None:
    room = Room()
    orch = new_run(tmp_path, "wall_height", room)
    request = orch.run_until_approval()
    debate_done = next(e for e in orch.session.bus.of_type("stage.completed") if e.payload["stage"] == "debate")
    assert debate_done.payload["rounds"] == 2 and debate_done.payload["stop_reason"] == "stances_unchanged"
    assert request["options"] == golden_pareto("wall_height")
    changes = orch.session.bus.of_type("stance.changed")
    assert {c.payload["agent"] for c in changes} >= {"cost", "time", "commercial"}
    stances = orch.session.blackboard.read("stances").content  # type: ignore[union-attr]
    assert set(stances) >= {"commercial", "round_1", "round_2"}
    debate = [m for m in orch.session.messages if m.stage == "debate" and m.intent != "VERIFY"]
    assert any(m.intent == "CHALLENGE" for m in debate) and all(m.to != "all" for m in debate)


def test_ask_agent_is_routed_and_answered(tmp_path: Path) -> None:
    room = Room()
    scripts = {"time": [tool_call("ask_agent", {"to": "contract", "question": "How is extension assessed?"})]}
    orch = new_run(tmp_path, "road_widening", room, scripts)
    orch.run_until_approval()
    sent = orch.session.bus.of_type("ask.sent")
    answered = orch.session.bus.of_type("ask.answered")
    assert len(sent) == 1 and sent[0].payload["from"] == "time" and sent[0].payload["to"] == "contract"
    answer_id = answered[0].payload["answer_message_id"]
    answer = orch.session.message(answer_id)
    assert answer.intent == "ANSWER" and answer.from_agent == "contract" and answer.to == "time"
    # The answer came back to the asker as the ask_agent tool result.
    ask_result = next(e for e in orch.session.bus.of_type("tool.result") if e.payload["tool"] == "ask_agent")
    assert ask_result.payload["ok"] and ask_result.payload["result"]["message_id"] == answer_id
    # The answer turn could not ask in turn (depth 1).
    contract_answer_call = [r for r in orch.llm.calls_for("contract")  # type: ignore[attr-defined]
                            if "asks you" in r.messages[1]["content"]]
    assert contract_answer_call and "ask_agent" not in contract_answer_call[0].tool_names


def test_failed_verification_gets_one_correction(tmp_path: Path) -> None:
    room = Room()
    scripts = {"cost": [tool_call("price_change"),
                        post("all", "ASSESS", "Direct cost is about AED 99,999 (clause 13.3).")]}
    orch = new_run(tmp_path, "paving_area", room, scripts)
    orch.run_until_approval()
    results = orch.session.bus.of_type("verification.result")
    first_fail = next(r for r in results if r.payload["agent"] == "cost" and r.payload["status"] == "fail")
    corrected = orch.session.bus.of_type("message.corrected")[0].payload
    assert corrected["original_message_id"] == first_fail.payload["message_id"]
    original = orch.session.message(corrected["original_message_id"])
    fixed = orch.session.message(corrected["corrected_message_id"])
    assert original.superseded_by == fixed.message_id and fixed.corrects == original.message_id
    assert fixed.verification.status == "pass"
    verify_notes = [m for m in orch.session.messages if m.from_agent == "verifier"]
    assert verify_notes and verify_notes[0].to == "cost" and verify_notes[0].intent == "VERIFY"


def test_second_failure_is_unresolved(tmp_path: Path) -> None:
    room = Room()
    bad = post("all", "ASSESS", "It costs 12345 in total.")
    orch = new_run(tmp_path, "paving_area", room, {"cost": [bad, bad]})
    orch.run_until_approval()
    cost_results = [r.payload for r in orch.session.bus.of_type("verification.result") if r.payload["agent"] == "cost"]
    assert cost_results[0]["status"] == "fail" and not cost_results[0]["unresolved"]
    assert cost_results[1]["status"] == "fail" and cost_results[1]["unresolved"]


def test_ask_limits(tmp_path: Path) -> None:
    room = Room()
    orch = new_run(tmp_path, "paving_area", room)
    session = orch.session
    token = current_turn.set(TurnState(agent="cost", depth=1))
    try:
        r = REGISTRY.dispatch(session, "ask_agent", {"to": "time", "question": "?"}, agent="cost")
        assert not r.ok and "cannot ask" in r.error
    finally:
        current_turn.reset(token)
    token = current_turn.set(TurnState(agent="cost", asks=2))
    try:
        r = REGISTRY.dispatch(session, "ask_agent", {"to": "time", "question": "?"}, agent="cost")
        assert not r.ok and "No more than 2" in r.error
    finally:
        current_turn.reset(token)
    r = REGISTRY.dispatch(session, "ask_agent", {"to": "cost", "question": "?"}, agent="cost")
    assert not r.ok


def test_verification_report_action_only_in_contractor_mode(tmp_path: Path) -> None:
    room = Room()
    orch = new_run(tmp_path, "road_widening", room)
    r = REGISTRY.dispatch(orch.session, "propose_action", {"type": "draft_verification_report", "reason": "x"},
                          agent="moderator")
    assert not r.ok and "contractor PVR mode" in r.error
    r = REGISTRY.dispatch(orch.session, "propose_action", {"type": "create_task", "reason": "x",
                                                           "payload": {"title": "New kerb rate"}}, agent="contract")
    assert not r.ok and "owner" in r.error
