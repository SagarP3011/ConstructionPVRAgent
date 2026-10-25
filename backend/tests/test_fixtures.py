"""The committed demo fixtures (fixtures/demo_run_<change_type>.jsonl) are good live runs that replay
offline: defaults, golden Pareto options, verified messages, approval before actions (SPEC 14, 16 Phase 4)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import fake_settings
from pvr.api.main import create_app
from pvr.api.runs import RunManager
from pvr.config import FIXTURES_DIR, GOLDEN_PATH
from pvr.data_loader import get_data
from pvr.events.snapshot import run_snapshot
from pvr.events.store import fixture_name, read_events
from test_api import read_sse

GOLDEN = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
CHANGE_TYPES = ["wall_height", "road_widening", "paving_area"]


def golden_pareto(change_type: str) -> list[str]:
    defaults = {p.name: p.default for p in get_data().change_type(change_type).parameters}
    case = next(c for c in GOLDEN["cases"] if c["change_type"] == change_type and c["parameters"] == defaults)
    return case["pareto_option_ids"]


@pytest.mark.parametrize("change_type", CHANGE_TYPES)
def test_fixture_is_a_good_complete_run(change_type: str) -> None:
    path = FIXTURES_DIR / f"{fixture_name(change_type)}.jsonl"
    assert path.is_file(), f"record it with: python -m pvr.cli save-fixture <run_id>"
    text = path.read_text(encoding="utf-8")
    assert "sk-" not in text and "OPENAI_API_KEY" not in text
    events = read_events(path)
    snap = run_snapshot(events)
    data = get_data()
    ct = data.change_type(change_type)

    assert snap.kind == "full" and snap.state == "completed"
    assert snap.context["parameters"] == {p.name: p.default for p in ct.parameters}
    assert snap.context["mode"] == ct.modes[0]
    assert [o["option_id"] for o in snap.options] == golden_pareto(change_type)

    types = [e.type for e in events]
    assert len({e.event_id for e in events}) == len(events) and len({e.run_id for e in events}) == 1
    assert types.index("approval.granted") < types.index("action.executed") and types[-1] == "run.completed"
    assert not [e for e in events if e.type == "verification.result" and e.payload["unresolved"]]
    assert not [e for e in events if e.type == "run.error"]

    baseline = [e for e in events if e.type == "tool.result" and e.payload["agent"] == "orchestrator"
                and e.payload["tool"] == "run_cpm"]
    assert len(baseline) == 1, "the baseline reference run for the Gantt chart is missing"

    rounds = snap.debate["rounds"]
    if len(golden_pareto(change_type)) == 1:
        assert rounds == 1 and snap.debate["stop_reason"] == "single_pareto_option"
    else:
        assert rounds >= 2 and "ask.sent" in types
        assert any(e.type == "message.posted" and e.payload["intent"] == "CHALLENGE" for e in events)

    outputs = FIXTURES_DIR / f"{fixture_name(change_type)}_outputs"
    assert (outputs / "pvr_output_form.json").is_file() and (outputs / "decision.json").is_file()


@pytest.mark.parametrize("change_type", CHANGE_TYPES)
def test_fixture_replays_without_api_key(change_type: str, tmp_path: Path) -> None:
    manager = RunManager(fake_settings(openai_api_key=""), runs_dir=tmp_path / "runs")
    client = TestClient(create_app(manager))
    name = fixture_name(change_type)
    events, reason = read_sse(client, f"/api/replay/{name}?speed=50&max_gap=0.001")
    assert reason == "run.completed"
    assert events == read_events(FIXTURES_DIR / f"{name}.jsonl")
    assert client.get(f"/api/runs/{name}/outputs/pvr_output_form.html").status_code == 200
