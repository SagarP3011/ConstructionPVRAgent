"""Decision replay: a recorded run brought back to its approval gate, so a person decides in the room."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from conftest import fake_settings
from pvr.config import FIXTURES_DIR
from pvr.data_loader import get_data
from pvr.events.store import read_events, save_fixture
from pvr.orchestrator.approvals import ApprovalError
from pvr.orchestrator.decision_replay import DecisionReplayError, events_until_decision, restore_for_decision
from test_api import Harness, read_sse

WALL = FIXTURES_DIR / "demo_run_wall_height.jsonl"
PERSON = {"approver_name": "Dana Ali", "approver_role": "Project Director"}


def recorded_run(harness: Harness, change_type: str = "wall_height") -> tuple[str, str]:
    """A completed run saved as a fixture, with its run folder removed: (fixture name, original run id)."""
    run_id = harness.start(change_type)
    harness.approve_all(run_id)
    fixture = save_fixture(run_id, harness.runs_dir, harness.fixtures_dir).stem
    shutil.rmtree(harness.runs_dir / run_id)
    return fixture, run_id


def test_a_recording_stops_at_its_decision_and_a_person_can_choose_another_option(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    fixture, original = recorded_run(harness)
    offline = Harness(tmp_path / "offline", api_key="")  # no API key: nothing after the gate calls a model
    offline.manager.fixtures_dir = harness.fixtures_dir
    client = offline.client

    response = client.post(f"/api/replay/{fixture}/decision")
    assert response.status_code == 201, response.text
    run_id = response.json()["run_id"]
    assert run_id != original

    # The replay plays the recording up to the approval request, then waits for the decision.
    played, _ = read_sse(client, f"/api/replay/{run_id}?speed=50&max_gap=0.01", stop_type="approval.requested")
    recorded = events_until_decision(read_events(harness.fixtures_dir / f"{fixture}.jsonl"))
    assert [e.event_id for e in played] == [e.event_id for e in recorded]
    assert all(e.run_id == run_id for e in played) and played[0].payload["replay_of"] == fixture
    assert "approval.granted" not in [e.type for e in played]
    snap = client.get(f"/api/runs/{run_id}").json()
    assert snap["state"] == "awaiting_approval" and snap["live"] is True and snap["replay_of"] == fixture
    assert not (offline.runs_dir / run_id / "outputs").exists()

    # The person chooses a different option from the one in the recording.
    actions = [a["action_id"] for a in snap["pending_actions"]]
    chosen = snap["options"][0]["option_id"]
    approved = client.post(f"/api/runs/{run_id}/approve", json={"option_id": chosen, "action_ids": actions, **PERSON})
    assert approved.status_code == 200, approved.text
    rest, reason = read_sse(client, f"/api/replay/{run_id}?after={played[-1].event_id}")
    assert reason == "run.completed" and rest[0].type == "approval.granted"
    assert [e.event_id for e in played + rest] == [f"E-{i:06d}" for i in range(1, len(played) + len(rest) + 1)]

    form = client.get(f"/api/runs/{run_id}/outputs/pvr_output_form.json").json()
    assert form["chosen_option"]["option_id"] == chosen and form["approver"]["name"] == PERSON["approver_name"]
    assert form["run_id"] == run_id
    listed = {r["id"]: r for r in client.get("/api/runs").json()}
    assert listed[run_id]["replay_of"] == fixture and listed[run_id]["chosen_option"] == chosen


def test_choosing_the_recorded_option_gives_the_recorded_outputs(tmp_path: Path) -> None:
    """The rebuilt state matches the live run: same messages, verification, stances and actions."""
    harness = Harness(tmp_path)
    fixture, _ = recorded_run(harness)
    path = harness.fixtures_dir / f"{fixture}.jsonl"
    events = read_events(path)
    granted = next(e for e in events if e.type == "approval.granted").payload
    orchestrator, sink = restore_for_decision(events, fixture, get_data(), fake_settings(), runs_dir=tmp_path / "again")
    try:
        orchestrator.approve(granted["option_id"], granted["approved_action_ids"], granted["approver_name"],
                             granted["approver_role"])
    finally:
        sink.close()
    out = orchestrator.session.run_dir / "outputs"
    recorded = harness.fixtures_dir / f"{fixture}_outputs"
    assert sorted(p.name for p in out.iterdir()) == sorted(p.name for p in recorded.iterdir())
    again = json.loads((out / "pvr_output_form.json").read_text(encoding="utf-8"))
    before = json.loads((recorded / "pvr_output_form.json").read_text(encoding="utf-8"))
    for key in ("run_id", "approver"):
        again.pop(key), before.pop(key)
    assert again == before


def test_the_demo_fixture_can_be_decided_again(tmp_path: Path) -> None:
    if not WALL.is_file():
        pytest.skip("no recorded wall fixture")
    orchestrator, sink = restore_for_decision(read_events(WALL), WALL.stem, get_data(), fake_settings(),
                                              runs_dir=tmp_path)
    sink.close()
    assert orchestrator.state == "awaiting_approval" and len(orchestrator.presented) >= 2
    with pytest.raises(ApprovalError, match="was not presented"):
        orchestrator.approve("OPT-UNKNOWN", [], "Dana Ali", "PD")


def test_a_recording_without_a_decision_cannot_be_decided(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    fixture, _ = recorded_run(harness, "paving_area")
    events = read_events(harness.fixtures_dir / f"{fixture}.jsonl")
    with pytest.raises(DecisionReplayError, match="never reached the decision"):
        events_until_decision(events[:10])
    with pytest.raises(DecisionReplayError, match="full multi-agent run"):
        events_until_decision(events[1:])
    path = harness.fixtures_dir / "demo_run_cut.jsonl"
    path.write_text("".join(e.model_dump_json() + "\n" for e in events[:10]), encoding="utf-8")
    assert harness.client.post("/api/replay/demo_run_cut/decision").status_code == 409
    assert harness.client.post("/api/replay/demo_run_nothing/decision").status_code == 404
