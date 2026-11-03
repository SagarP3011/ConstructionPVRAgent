"""Rates and assumptions endpoints: read-only, consistent with the work rates, and made of engine outputs."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import fake_settings
from pvr.api.assumptions import CREWS_PATH, build_example, load_crews
from pvr.api.main import create_app
from pvr.api.runs import RunManager
from pvr.config import DATA_DIR
from pvr.data_loader import get_data
from pvr.engines.change import make_context
from pvr.engines.cost import price_change
from pvr.engines.options import evaluate_option
from pvr.engines.productivity import added_duration

DATA = get_data()


def _hashes(folder: Path) -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir()) if p.is_file()}


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    manager = RunManager(fake_settings(), runs_dir=tmp_path / "runs", fixtures_dir=tmp_path / "fixtures")
    return TestClient(create_app(manager))


def test_every_work_rate_has_a_crew() -> None:
    crew_activities = {c.activity_id for c in load_crews().crews}
    assert {p.activity_id for p in DATA.productivity.items} <= crew_activities
    schedule_ids = {a.id for a in DATA.schedule.activities}
    assert crew_activities <= schedule_ids


def test_labour_hours_follow_from_crew_and_output(client: TestClient) -> None:
    body = client.get("/api/assumptions").json()
    output = {p.boq_code: p.productivity for p in DATA.productivity.items}
    seen = set()
    for crew in body["crews"]["items"]:
        assert crew["people"] == sum(t["count"] for t in crew["trades"])
        for item in crew["work_items"]:
            expected = crew["people"] * crew["hours_per_day"] / output[item["boq_code"]]
            assert item["labour_hours_per_unit"] == pytest.approx(expected, abs=0.0005)
            seen.add(item["boq_code"])
    assert seen == set(output)
    assert body["crews"]["status"] == "Assumed for this proof of concept"


def test_assumptions_show_the_data_file_values(client: TestClient) -> None:
    body = client.get("/api/assumptions").json()
    assert body["cost"]["time_related_cost_per_working_day_aed"] == DATA.commercial.time_related_cost_per_working_day_aed
    assert body["time"]["time_buffer_working_days"] == DATA.project.time_buffer_working_days
    assert body["work_rates"]["rule"] == DATA.productivity.rule
    assert [r["change_type"] for r in body["quantity_rules"]] == [ct.id for ct in DATA.scenario.change_types]


@pytest.mark.parametrize("change_type", [ct.id for ct in DATA.scenario.change_types])
def test_worked_example_matches_the_engines(client: TestClient, change_type: str) -> None:
    response = client.get(f"/api/assumptions/example/{change_type}")
    assert response.status_code == 200, response.text
    body = response.json()
    ctx = make_context(DATA, change_type)
    assert body["cost"]["direct_cost_aed"] == price_change(ctx, DATA).direct_cost_aed
    assert [d["added_days"] for d in body["durations"]] == [a.added_days for a in added_duration(ctx, DATA).activities]
    assert body["no_extra_crews"]["total_cost_aed"] == evaluate_option(ctx, DATA, []).total_cost_aed


def test_worked_example_takes_the_selected_size(client: TestClient) -> None:
    body = client.get("/api/assumptions/example/wall_height?new_height_m=3.0").json()
    assert body == build_example(DATA, "wall_height", {"new_height_m": 3.0}) | {"parameters": body["parameters"]}
    assert body["parameters"]["new_height_m"] == 3.0


def test_worked_example_rejects_bad_input(client: TestClient) -> None:
    assert client.get("/api/assumptions/example/no_such_change").status_code == 422
    assert client.get("/api/assumptions/example/wall_height?new_height_m=abc").status_code == 422
    assert client.get("/api/assumptions/example/wall_height?new_height_m=9").status_code == 422


def test_endpoints_are_read_only(client: TestClient, tmp_path: Path) -> None:
    before = (_hashes(DATA_DIR), CREWS_PATH.read_bytes())
    client.get("/api/assumptions")
    client.get("/api/assumptions/example/road_widening")
    assert (_hashes(DATA_DIR), CREWS_PATH.read_bytes()) == before
    assert not (tmp_path / "runs").exists() or not any((tmp_path / "runs").iterdir())
    assert client.post("/api/assumptions").status_code == 405
