"""API with FakeLLM: REST routes, SSE streaming and resume, approval through the API, run store, replay."""

from __future__ import annotations

import json
import shutil
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from conftest import fake_settings
from fake_room import Room
from pvr.api.main import create_app
from pvr.api.runs import RunManager
from pvr.events.store import read_events, replay_delays, save_fixture
from pvr.llm.client import LLM, LLMError, LLMResponse
from pvr.models import Event

PARETO = {"paving_area": ["OPT-NONE"], "wall_height": ["OPT-A320", "OPT-A340", "OPT-NONE"]}


class GatedLLM:
    """Holds every call until the test has handed the run's session to the fake room."""

    def __init__(self, inner: LLM, gate: threading.Event) -> None:
        self.inner = inner
        self.gate = gate

    def complete(self, **kwargs: Any) -> LLMResponse:
        assert self.gate.wait(10), "the test never opened the gate"
        return self.inner.complete(**kwargs)


class Harness:
    """An app with a fake room, temporary run and fixture folders, and a TestClient."""

    def __init__(self, tmp_path: Path, api_key: str = "fake-key") -> None:
        self.room = Room()
        self.gate = threading.Event()
        self.runs_dir = tmp_path / "runs"
        self.fixtures_dir = tmp_path / "fixtures"
        self.manager = RunManager(fake_settings(openai_api_key=api_key), runs_dir=self.runs_dir,
                                  fixtures_dir=self.fixtures_dir,
                                  llm_factory=lambda _settings: GatedLLM(self.room.llm(), self.gate))
        self.client = TestClient(create_app(self.manager))

    def start(self, change_type: str, **body: Any) -> str:
        response = self.client.post("/api/runs", json={"change_type": change_type, **body})
        assert response.status_code == 201, response.text
        run_id = response.json()["run_id"]
        live = self.manager.get(run_id)
        assert live is not None
        self.room.session = live.orchestrator.session
        self.gate.set()
        return run_id

    def wait_for_state(self, run_id: str, *states: str, timeout: float = 30.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            snap = self.client.get(f"/api/runs/{run_id}").json()
            if snap["state"] in states:
                return snap
            time.sleep(0.05)
        raise AssertionError(f"run {run_id} never reached {states}")

    def approve_all(self, run_id: str, option_index: int = 0) -> dict[str, Any]:
        snap = self.wait_for_state(run_id, "awaiting_approval")
        body = {"option_id": snap["options"][option_index]["option_id"],
                "action_ids": [a["action_id"] for a in snap["pending_actions"]],
                "approver_name": "Sam Lee", "approver_role": "Project Director"}
        response = self.client.post(f"/api/runs/{run_id}/approve", json=body)
        assert response.status_code == 200, response.text
        return response.json()


def read_sse(client: TestClient, url: str, stop_type: str | None = None,
             headers: dict[str, str] | None = None) -> tuple[list[Event], str | None]:
    """Read an SSE stream into events. Stops at the `end` event (returns its reason), or right after
    an event of `stop_type` (returns None)."""
    events: list[Event] = []
    name = "message"
    with client.stream("GET", url, headers=headers or {}) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        for line in response.iter_lines():
            if line.startswith("event: "):
                name = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
                if name == "end":
                    return events, data["reason"]
                events.append(Event.model_validate(data))
                if stop_type and events[-1].type == stop_type:
                    return events, None
            elif line == "":
                name = "message"
    raise AssertionError("stream closed without an end event")


@pytest.fixture
def harness(tmp_path: Path) -> Harness:
    return Harness(tmp_path)


# --- reference data -------------------------------------------------------------------------------------


def test_health_reports_whether_live_runs_are_available(tmp_path: Path) -> None:
    assert Harness(tmp_path).client.get("/api/health").json()["live_runs_available"] is True
    body = Harness(tmp_path, api_key="").client.get("/api/health").json()
    assert body["status"] == "ok" and body["live_runs_available"] is False


def test_change_types_and_data_files(harness: Harness) -> None:
    types = harness.client.get("/api/change-types").json()
    assert [t["id"] for t in types] == ["wall_height", "road_widening", "paving_area"]
    assert all(t["parameters"] and t["modes"] for t in types)
    assert len(harness.client.get("/api/data/boq").json()) == 38
    assert harness.client.get("/api/data/contract").status_code == 200
    assert harness.client.get("/api/data/secrets").status_code == 404


# --- starting runs -----------------------------------------------------------------------------------------


@pytest.mark.parametrize("body", [
    {"change_type": "garden_shed"},
    {"change_type": "wall_height", "parameters": {"new_height_m": 9.0}},
    {"change_type": "wall_height", "parameters": {"new_height_m": 2.8}, "mode": "contractor_pvr"},
    {"change_type": "paving_area", "mode": "contractor_pvr"},
    {"change_type": "paving_area", "parameters": {"colour": 1}},
])
def test_invalid_runs_are_rejected_before_any_model_call(harness: Harness, body: dict[str, Any]) -> None:
    response = harness.client.post("/api/runs", json=body)
    assert response.status_code == 422, response.text
    assert not harness.runs_dir.exists()


def test_without_api_key_live_runs_return_503(tmp_path: Path) -> None:
    manager = RunManager(fake_settings(openai_api_key=""), runs_dir=tmp_path / "runs",
                         fixtures_dir=tmp_path / "fixtures")  # the real OpenAI factory
    response = TestClient(create_app(manager)).post("/api/runs", json={"change_type": "paving_area"})
    assert response.status_code == 503 and "Replays still work" in response.json()["detail"]


# --- a live run through the API ----------------------------------------------------------------------------


def test_live_stream_approval_and_outputs(harness: Harness) -> None:
    run_id = harness.start("wall_height", mode="contractor_pvr")
    client = harness.client

    # Watch the run live until it asks for approval, then drop the connection.
    first, _ = read_sse(client, f"/api/runs/{run_id}/events", stop_type="approval.requested")
    assert first[0].type == "run.started" and first[-1].type == "approval.requested"
    assert "action.executed" not in [e.type for e in first]

    snap = harness.wait_for_state(run_id, "awaiting_approval")
    assert snap["live"] is True and [o["option_id"] for o in snap["options"]] == PARETO["wall_height"]
    assert {a["type"] for a in snap["pending_actions"]} >= {"draft_pvr_form", "notify"}
    assert all(a["status"] == "pending" for a in snap["pending_actions"])
    # Nothing is executed before approval.
    assert not (harness.runs_dir / run_id / "outputs").exists()
    assert client.get(f"/api/runs/{run_id}/outputs/pvr_output_form.json").status_code == 404

    url = f"/api/runs/{run_id}/approve"
    person = {"approver_name": "Sam Lee", "approver_role": "Project Director"}
    assert client.post(url, json={"option_id": "OPT-A330", **person}).status_code == 400  # not presented
    assert client.post(url, json={"option_id": "OPT-A340", "approver_name": " ",
                                  "approver_role": "x"}).status_code == 400  # no name
    result = harness.approve_all(run_id, option_index=1)
    assert result["option_id"] == "OPT-A340" and result["executed_actions"]
    assert client.post(url, json={"option_id": "OPT-A340", **person}).status_code == 409  # already decided
    assert client.post(f"/api/runs/{run_id}/reject", json={**person, "reason": "x"}).status_code == 409

    # Resume after the last event seen, with Last-Event-ID, and read to the end.
    rest, reason = read_sse(client, f"/api/runs/{run_id}/events", headers={"Last-Event-ID": first[-1].event_id})
    assert reason == "run.completed"
    streamed = first + rest
    stored = read_events(harness.runs_dir / run_id / "events.jsonl")
    assert [e.event_id for e in streamed] == [e.event_id for e in stored]
    assert streamed == stored
    order = [e.type for e in streamed]
    assert order.index("approval.granted") < order.index("action.executed") and order[-1] == "run.completed"

    snap = client.get(f"/api/runs/{run_id}").json()
    assert snap["state"] == "completed" and snap["decision"]["option_id"] == "OPT-A340"
    assert {a["status"] for a in snap["pending_actions"]} == {"executed"}
    form = client.get(f"/api/runs/{run_id}/outputs/pvr_output_form.json")
    assert form.status_code == 200 and form.json()["chosen_option"]["option_id"] == "OPT-A340"
    assert client.get(f"/api/runs/{run_id}/outputs/notifications.json").status_code == 200
    assert client.get(f"/api/runs/{run_id}/outputs/..%2Fevents.jsonl").status_code == 404
    assert client.get(f"/api/runs/{run_id}/outputs/missing.json").status_code == 404

    listed = {r["id"]: r for r in client.get("/api/runs").json()}
    assert listed[run_id]["state"] == "completed" and listed[run_id]["chosen_option"] == "OPT-A340"


def test_reject_through_api_executes_nothing(harness: Harness) -> None:
    run_id = harness.start("paving_area")
    harness.wait_for_state(run_id, "awaiting_approval")
    url = f"/api/runs/{run_id}/reject"
    assert harness.client.post(url, json={"approver_name": "Sam Lee", "approver_role": "PD",
                                          "reason": " "}).status_code == 400
    response = harness.client.post(url, json={"approver_name": "Sam Lee", "approver_role": "PD", "reason": "Not now"})
    assert response.status_code == 200 and response.json()["status"] == "rejected"
    events, reason = read_sse(harness.client, f"/api/runs/{run_id}/events")
    assert reason == "run.completed" and "action.executed" not in [e.type for e in events]
    assert harness.client.get(f"/api/runs/{run_id}").json()["state"] == "rejected"
    assert not (harness.runs_dir / run_id / "outputs").exists()
    approve = {"option_id": "OPT-NONE", "approver_name": "Sam Lee", "approver_role": "PD"}
    assert harness.client.post(f"/api/runs/{run_id}/approve", json=approve).status_code == 409


def test_unknown_runs_return_404(harness: Harness) -> None:
    for path in ("/api/runs/R-nope", "/api/runs/R-nope/events", "/api/replay/R-nope",
                 "/api/runs/R-nope/outputs/tasks.json", "/api/replay/..%2F..%2Fdata%2Fboq"):
        assert harness.client.get(path).status_code == 404, path
    person = {"approver_name": "A", "approver_role": "B"}
    assert harness.client.post("/api/runs/R-nope/approve", json={"option_id": "OPT-NONE", **person}).status_code == 409


def test_an_unreachable_model_fails_the_run_instead_of_asking_for_approval(tmp_path: Path) -> None:
    class NoQuota:
        def complete(self, **_: Any) -> LLMResponse:
            raise LLMError("RateLimitError: insufficient_quota")

    manager = RunManager(fake_settings(openai_api_key="k"), runs_dir=tmp_path / "runs",
                         fixtures_dir=tmp_path / "fixtures", llm_factory=lambda _s: NoQuota())
    client = TestClient(create_app(manager))
    run_id = client.post("/api/runs", json={"change_type": "paving_area"}).json()["run_id"]
    events, reason = read_sse(client, f"/api/runs/{run_id}/events")
    assert reason == "run.error" and "could not reach the language model" in events[-1].payload["error"]
    assert "approval.requested" not in [e.type for e in events]
    assert client.get(f"/api/runs/{run_id}").json()["state"] == "failed"


def test_a_failing_run_ends_with_a_fatal_error(tmp_path: Path) -> None:
    class Broken:
        def complete(self, **_: Any) -> LLMResponse:
            raise RuntimeError("model fell over")

    manager = RunManager(fake_settings(openai_api_key="k"), runs_dir=tmp_path / "runs",
                         fixtures_dir=tmp_path / "fixtures", llm_factory=lambda _s: Broken())
    client = TestClient(create_app(manager))
    run_id = client.post("/api/runs", json={"change_type": "paving_area"}).json()["run_id"]
    events, reason = read_sse(client, f"/api/runs/{run_id}/events")
    assert reason == "run.error" and events[-1].payload["fatal"] is True
    assert "model fell over" in events[-1].payload["error"]
    assert client.get(f"/api/runs/{run_id}").json()["state"] == "failed"


# --- run store and replay -----------------------------------------------------------------------------------


def test_stored_run_and_fixture_replay_without_api_key(harness: Harness, tmp_path: Path) -> None:
    run_id = harness.start("paving_area")
    harness.approve_all(run_id)
    stored = read_events(harness.runs_dir / run_id / "events.jsonl")

    target = save_fixture(run_id, harness.runs_dir, harness.fixtures_dir)
    assert target.name == "demo_run_paving_area.jsonl"
    assert (harness.fixtures_dir / "demo_run_paving_area_outputs" / "pvr_output_form.json").is_file()
    shutil.rmtree(harness.runs_dir)  # replay must not need the original run folder

    # A fresh server with no API key replays the fixture.
    offline = Harness(tmp_path / "offline", api_key="")
    offline.manager.fixtures_dir = harness.fixtures_dir
    client = offline.client
    replayed, reason = read_sse(client, "/api/replay/demo_run_paving_area?speed=50&max_gap=0.01")
    assert reason == "run.completed" and replayed == stored

    resumed, _ = read_sse(client, f"/api/replay/demo_run_paving_area?speed=50&after={stored[9].event_id}")
    assert resumed == stored[10:]
    assert client.get("/api/replay/demo_run_paving_area?speed=0").status_code == 422

    # Snapshot, listing and outputs work for the fixture, by fixture name and by original run id.
    snap = client.get("/api/runs/demo_run_paving_area").json()
    assert snap["state"] == "completed" and snap["live"] is False and snap["run_id"] == run_id
    assert [r["id"] for r in client.get("/api/runs").json()] == ["demo_run_paving_area"]
    for trace_id in ("demo_run_paving_area", run_id):
        assert client.get(f"/api/runs/{trace_id}/outputs/pvr_output_form.html").status_code == 200
    events, reason = read_sse(client, "/api/runs/demo_run_paving_area/events")
    assert events == stored and reason == "run.completed"


def test_save_fixture_refuses_unfinished_runs(harness: Harness) -> None:
    run_id = harness.start("paving_area")
    harness.wait_for_state(run_id, "awaiting_approval")
    with pytest.raises(ValueError, match="approval"):
        save_fixture(run_id, harness.runs_dir, harness.fixtures_dir)
    with pytest.raises(FileNotFoundError):
        save_fixture("R-nope", harness.runs_dir, harness.fixtures_dir)


def _event(i: int, ts: str) -> Event:
    return Event(event_id=f"E-{i:06d}", run_id="R-x", type="tool.called", ts=ts)


def test_replay_delays_follow_original_timing_scaled_and_capped() -> None:
    events = [_event(1, "2026-10-25T10:00:00.000+00:00"), _event(2, "2026-10-25T10:00:01.000+00:00"),
              _event(3, "2026-10-25T10:00:11.000+00:00"), _event(4, "2026-10-25T10:00:11.000+00:00")]
    assert replay_delays(events, speed=2, max_gap_s=3) == [0.0, 0.5, 1.5, 0.0]
    assert replay_delays(events, speed=1, max_gap_s=0) == [0.0, 1.0, 10.0, 0.0]
    with pytest.raises(ValueError):
        replay_delays(events, speed=0)
