"""Deterministic engines against every value in tests_golden/golden.json, plus validation."""

from __future__ import annotations

import ast
import json
from datetime import date
from pathlib import Path

import pytest

from pvr.config import GOLDEN_PATH
from pvr.data_loader import get_data
from pvr.engines import boq, buffer, change, contract, cost, cpm, options, productivity, quantities
from pvr.engines.common import EngineError
from pvr.models import Overrides, RunContext

DATA = get_data()
GOLDEN = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
CASES = GOLDEN["cases"]


def case_id(case: dict) -> str:
    return case["change_type"] + "-" + "-".join(f"{v:g}" for v in case["parameters"].values())


def ctx_for(case: dict) -> RunContext:
    return change.make_context(DATA, case["change_type"], case["parameters"])


approx = pytest.approx


# --- baseline schedule ------------------------------------------------------------


def test_baseline_cpm() -> None:
    result = cpm.run_cpm(DATA)
    base = GOLDEN["baseline"]
    assert result.completion_working_day == base["completion_working_day"]
    assert result.completion_date.isoformat() == base["completion_date"]
    assert result.critical_path == base["critical_path"]
    for aid, expected in base["activities"].items():
        timing = result.activities[aid]
        assert (timing.ES, timing.EF, timing.TF) == (expected["ES"], expected["EF"], expected["TF"]), aid


def test_employer_commitment_date() -> None:
    commitment = GOLDEN["employer_commitment"]
    assert cpm.finish_date(commitment["working_day"], DATA.project.calendar).isoformat() == commitment["date"]


def test_working_day_zero_is_calendar_start() -> None:
    assert cpm.working_day_to_date(0, DATA.project.calendar) == date(2026, 10, 26)
    assert cpm.working_day_to_date(6, DATA.project.calendar) == date(2026, 11, 2)  # skips Sunday


def test_cpm_detects_cycles() -> None:
    acts = [a.model_dump() for a in DATA.schedule.activities]
    first = next(a for a in acts if a["id"] == "A010")
    first["predecessors"] = [{"id": "A920", "type": "FS", "lag": 0}]
    looped = DATA.model_copy(update={"schedule": DATA.schedule.model_copy(
        update={"activities": [type(DATA.schedule.activities[0]).model_validate(a) for a in acts]})})
    with pytest.raises(EngineError, match="cycle"):
        cpm.run_cpm(looped)


# --- every golden case --------------------------------------------------------------


@pytest.mark.parametrize("case", CASES, ids=case_id)
def test_quantities(case: dict) -> None:
    q = quantities.quantify_change(ctx_for(case), DATA)
    assert q.deltas() == approx(case["quantity_delta"])
    assert set(q.deltas()) == set(case["quantity_delta"])
    assert [(r.code, r.reason) for r in q.requires_review] == [(r["code"], r["reason"]) for r in case["requires_review"]]
    assert [u.code for u in q.unaffected] == case["unaffected"]


@pytest.mark.parametrize("case", CASES, ids=case_id)
def test_cost(case: dict) -> None:
    result = cost.price_change(ctx_for(case), DATA)
    assert {line.code: line.amount_aed for line in result.lines} == approx(case["cost_lines"])
    assert result.direct_cost_aed == approx(case["direct_cost_aed"])
    assert result.rate_source == "BOQ rate, clause 13.3"
    assert all(i.amount_aed == 0 for i in result.unpriced_items)
    assert [i.code for i in result.unpriced_items] == [r["code"] for r in case["requires_review"]]


@pytest.mark.parametrize("case", CASES, ids=case_id)
def test_added_duration(case: dict) -> None:
    impact = productivity.added_duration(ctx_for(case), DATA)
    assert {a.activity_id: a.added_days for a in impact.activities} == case["added_duration"]
    assert impact.new_durations() == case["new_durations"]


@pytest.mark.parametrize("case", CASES, ids=case_id)
def test_impacted_completion(case: dict) -> None:
    impact = productivity.added_duration(ctx_for(case), DATA)
    result = cpm.run_cpm(DATA, impact.new_durations())
    assert result.completion_working_day == case["impacted_completion_working_day_no_acceleration"]


OPTION_FIELDS = (
    "option_id", "extra_crews_on", "completion_working_day", "delay_working_days", "acceleration_cost_aed",
    "time_related_cost_aed", "total_cost_aed", "time_buffer_remaining_days", "contingency_remaining_aed",
)


@pytest.mark.parametrize("case", CASES, ids=case_id)
def test_all_options(case: dict) -> None:
    search = options.search_options(ctx_for(case), DATA)
    assert len(search.options) == len(case["options_all"])
    for got, expected in zip(search.options, case["options_all"]):
        for field in OPTION_FIELDS:
            assert getattr(got, field) == approx(expected[field]), (expected["option_id"], field)
        assert got.completion_date.isoformat() == expected["completion_date"], expected["option_id"]
        none = case["options_all"][0]
        assert got.cost_above_no_crews_aed == approx(expected["total_cost_aed"] - none["total_cost_aed"])
        assert got.delay_saved_vs_no_crews_days == none["delay_working_days"] - expected["delay_working_days"]


@pytest.mark.parametrize("case", CASES, ids=case_id)
def test_pareto(case: dict) -> None:
    search = options.search_options(ctx_for(case), DATA)
    assert search.pareto_option_ids == case["pareto_option_ids"]


@pytest.mark.parametrize("case", CASES, ids=case_id)
def test_check_buffer_matches_options(case: dict) -> None:
    ctx = ctx_for(case)
    for expected in case["options_all"]:
        check = buffer.check_buffer(ctx, DATA, expected["option_id"])
        assert check.time_buffer_remaining_days == expected["time_buffer_remaining_days"]
        assert check.contingency_remaining_aed == approx(expected["contingency_remaining_aed"])
        assert check.within_contingency == (expected["contingency_remaining_aed"] >= 0)
        assert check.budget_uplift_needed_aed == approx(max(0.0, -expected["contingency_remaining_aed"]))
        assert check.exceeds_employer_commitment == (expected["time_buffer_remaining_days"] < 0)


# --- contractor claim and notice ------------------------------------------------------


def wall_contractor_ctx() -> RunContext:
    return change.make_context(DATA, "wall_height", mode="contractor_pvr")


def test_contractor_claim_comparison() -> None:
    expected = GOLDEN["contractor_claim_wall_2_5"]
    result = cost.compare_contractor_claim(wall_contractor_ctx(), DATA)
    assert result.claimed_subtotal_aed == approx(expected["claimed_subtotal_aed"])
    assert result.claimed_preliminaries_aed == approx(expected["claimed_preliminaries_aed"])
    assert result.claimed_total_aed == approx(expected["claimed_total_aed"])
    assert result.stated_total_matches_lines
    assert result.claimed_extension_days == expected["claimed_extension_days"]
    assert result.assessed_direct_cost_aed == approx(expected["assessed_direct_cost_aed"])
    assert result.difference_direct_aed == approx(expected["difference_direct_aed"])
    assert result.assessed_extension_days_without_acceleration == expected["assessed_extension_days_without_acceleration"]
    assert result.allowed_preliminaries_aed == 0
    assert [line.matched_code for line in result.lines] == ["B-04-010", "B-04-020", "B-04-040", "B-04-015"]
    assert {a.clause for a in result.adjustments} >= {"13.3", "13.4", "8.4"}


def test_contractor_claim_rejected_in_what_if_mode() -> None:
    with pytest.raises(EngineError):
        cost.compare_contractor_claim(change.make_context(DATA, "wall_height"), DATA)


def test_notice_check() -> None:
    expected = GOLDEN["notice_check_wall"]
    result = contract.check_notice(date.fromisoformat(expected["instruction_date"]),
                                   date.fromisoformat(expected["pvr_date"]))
    assert result.calendar_days == expected["calendar_days"]
    assert result.within_limit == expected["within_28_days"]
    claim = cost.compare_contractor_claim(wall_contractor_ctx(), DATA)
    assert claim.notice.calendar_days == expected["calendar_days"]


def test_notice_out_of_time_and_reversed_dates() -> None:
    assert not contract.check_notice(date(2026, 11, 2), date(2026, 12, 1)).within_limit
    with pytest.raises(EngineError):
        contract.check_notice(date(2026, 11, 4), date(2026, 11, 2))


# --- overrides ----------------------------------------------------------------------------


def test_contingency_and_buffer_overrides() -> None:
    ctx = change.make_context(
        DATA, "wall_height", overrides=Overrides(cost_contingency_remaining_aed=75000, time_buffer_working_days=5),
    )
    a320 = buffer.check_buffer(ctx, DATA, "OPT-A320")
    assert a320.within_contingency and a320.budget_uplift_needed_aed == 0
    none = buffer.check_buffer(ctx, DATA, "OPT-NONE")
    assert none.exceeds_employer_commitment and none.time_buffer_remaining_days < 0


# --- change engine and validation --------------------------------------------------------


def test_list_change_types() -> None:
    assert [c.id for c in change.list_change_types(DATA)] == ["wall_height", "road_widening", "paving_area"]


def test_change_request_texts() -> None:
    wall = change.get_change_request(wall_contractor_ctx(), DATA)
    assert wall.id == "CR-wall_height-1"
    assert "2.5 m" in wall.instruction_text
    assert wall.variation_instruction and wall.variation_instruction.ref == "VI-017"
    assert wall.contractor_pvr and wall.contractor_pvr.ref == "PVR-023"
    road = change.get_change_request(change.make_context(DATA, "road_widening"), DATA)
    assert "by 1.0 m over 600 m" in road.instruction_text
    assert road.contractor_pvr is None
    paving = change.get_change_request(change.make_context(DATA, "paving_area"), DATA)
    assert "Add 400 m2" in paving.instruction_text


def test_compare_drawing_revisions() -> None:
    wall = change.compare_drawing_revisions(change.make_context(DATA, "wall_height"), DATA)
    assert (wall.drawing, wall.from_revision, wall.to_revision) == ("L-201", "B", "C")
    assert [(c.parameter, c.old, c.new) for c in wall.changes] == [("wall_height_m", 2.0, 2.5)]
    what_if = change.compare_drawing_revisions(change.make_context(DATA, "wall_height", {"new_height_m": 2.8}), DATA)
    assert what_if.to_revision is None
    road = change.compare_drawing_revisions(change.make_context(DATA, "road_widening"), DATA)
    assert road.changes[0].new == approx(9.0)
    assert "internal_road" == road.element


@pytest.mark.parametrize(
    ("change_type", "params", "mode"),
    [
        ("wall_height", {"new_height_m": 3.1}, "internal_what_if"),
        ("wall_height", {"new_height_m": 2.0}, "internal_what_if"),
        ("wall_height", {"new_height_m": 2.55}, "internal_what_if"),
        ("road_widening", {"widen_by_m": 2.5, "length_m": 600}, "internal_what_if"),
        ("road_widening", {"widen_by_m": 1.0, "length_m": 50}, "internal_what_if"),
        ("paving_area", {"added_area_m2": 1600}, "internal_what_if"),
        ("paving_area", {"added_area_m2": 125}, "internal_what_if"),
        ("paving_area", {"area": 400}, "internal_what_if"),
        ("road_widening", {}, "contractor_pvr"),
        ("wall_height", {"new_height_m": 3.0}, "contractor_pvr"),
        ("bridge", {}, "internal_what_if"),
    ],
)
def test_invalid_contexts_rejected(change_type: str, params: dict, mode: str) -> None:
    with pytest.raises(EngineError):
        change.make_context(DATA, change_type, params, mode=mode)  # type: ignore[arg-type]


def test_engines_validate_hand_built_context() -> None:
    bad = RunContext(change_type="wall_height", parameters={"new_height_m": 9.0})
    with pytest.raises(EngineError):
        quantities.quantify_change(bad, DATA)


def test_invalid_options_rejected() -> None:
    ctx = change.make_context(DATA, "wall_height")
    with pytest.raises(EngineError, match="Not eligible"):
        options.evaluate_option(ctx, DATA, ["A100"])
    with pytest.raises(EngineError, match="extra crew"):
        options.evaluate_option(ctx, DATA, ["A320", "A320"])
    with pytest.raises(EngineError):
        buffer.check_buffer(ctx, DATA, "PLAN-B")


def test_option_id_uses_schedule_order() -> None:
    ctx = change.make_context(DATA, "wall_height")
    assert options.evaluate_option(ctx, DATA, ["A340", "A320"]).option_id == "OPT-A320-A340"


# --- search ---------------------------------------------------------------------------------


def test_search_boq() -> None:
    hits = boq.search_boq("blockwork boundary wall", DATA)
    assert hits[0].code == "B-04-010"
    exact = boq.search_boq("R-02-050 kerbs", DATA)
    assert exact[0].code == "R-02-050" and exact[0].exact_code_match
    assert len(boq.search_boq("paving", DATA, top_k=2)) <= 2
    assert boq.get_boq_item("l-05-050", DATA).rate_aed == 92
    with pytest.raises(EngineError):
        boq.get_boq_item("X-99-999", DATA)


def test_search_contract() -> None:
    assert contract.search_contract("extension of time critical path float", DATA)[0].clause == "8.4"
    assert contract.search_contract("percentage addition for preliminaries", DATA)[0].clause == "13.4"
    assert contract.search_contract("clause 20.1", DATA)[0].clause == "20.1"
    assert contract.get_clause("13.3", DATA).title == "Valuation of Variations"
    with pytest.raises(EngineError):
        contract.get_clause("99.9", DATA)


# --- purity ----------------------------------------------------------------------------------

FORBIDDEN_IMPORTS = ("openai", "anthropic", "pvr.llm", "pvr.agents", "pvr.orchestrator", "pvr.tools", "httpx")


def test_engines_have_no_llm_imports() -> None:
    engines_dir = Path(cpm.__file__).parent
    for path in engines_dir.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                assert not name.startswith(FORBIDDEN_IMPORTS), f"{path.name} imports {name}"
