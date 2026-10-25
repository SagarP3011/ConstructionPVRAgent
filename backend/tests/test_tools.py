"""Tool layer: schemas, run context injection, input validation and fact registration."""

from __future__ import annotations

import json
import re
from typing import Any

import pytest

from conftest import make_session
from pvr.tools.facts import FactRegistry, infer_unit, units_match
from pvr.tools.registry import REGISTRY, clean_schema

ENGINE_TOOLS = [
    "get_change_request", "compare_drawing_revisions", "check_notice", "search_contract", "get_clause",
    "quantify_change", "search_boq", "get_boq_item", "price_change", "compare_contractor_claim", "check_buffer",
    "added_duration", "run_cpm", "evaluate_option", "search_options",
]
CONTEXT_FIELDS = {"change_type", "parameters", "mode", "overrides", "ctx", "new_height_m", "widen_by_m",
                  "length_m", "added_area_m2"}


def numeric_leaves(node: Any, path: str = "") -> list[tuple[str, float]]:
    if isinstance(node, bool) or node is None:
        return []
    if isinstance(node, (int, float)):
        return [(path, float(node))]
    if isinstance(node, dict):
        return [x for k, v in node.items() for x in numeric_leaves(v, f"{path}.{k}" if path else k)]
    if isinstance(node, list):
        return [x for i, v in enumerate(node) for x in numeric_leaves(v, f"{path}[{i}]")]
    return []


# --- schemas -------------------------------------------------------------------------------------


def test_every_engine_tool_is_registered() -> None:
    assert set(ENGINE_TOOLS) <= set(REGISTRY.names())
    assert {"post_message", "read_blackboard"} <= set(REGISTRY.names())


@pytest.mark.parametrize("name", REGISTRY.names())
def test_schema_is_valid_function_definition(name: str) -> None:
    schema = REGISTRY.get(name).openai_schema()
    assert schema["type"] == "function"
    fn = schema["function"]
    assert fn["name"] == name and fn["description"]
    params = fn["parameters"]
    assert params["type"] == "object" and params["additionalProperties"] is False
    text = json.dumps(params)
    assert "$ref" not in text and '"title"' not in text
    # Context injection: agents never pass change parameters themselves.
    assert not CONTEXT_FIELDS & set(params["properties"])


def test_clean_schema_inlines_nested_models() -> None:
    claims = REGISTRY.get("post_message").openai_schema()["function"]["parameters"]["properties"]["claims"]
    assert set(claims["items"]["properties"]) == {"label", "value", "unit", "fact_id"}
    assert clean_schema({"type": "object"})["properties"] == {}


# --- context injection ----------------------------------------------------------------------------


def test_same_call_uses_each_runs_context() -> None:
    wall = make_session("wall_height")
    road = make_session("road_widening", {"widen_by_m": 2.0, "length_m": 1500})
    w = REGISTRY.dispatch(wall, "price_change", "{}", agent="cost")
    r = REGISTRY.dispatch(road, "price_change", "{}", agent="cost")
    assert w.ok and r.ok
    assert w.result["direct_cost_aed"] != r.result["direct_cost_aed"]
    assert {line["code"] for line in w.result["lines"]} == {"B-04-010", "B-04-015", "B-04-020", "B-04-040"}
    assert r.result["lines"][0]["code"].startswith("R-02")


def test_contractor_claim_tool_only_in_contractor_mode() -> None:
    what_if = make_session("wall_height")
    contractor = make_session("wall_height", mode="contractor_pvr")
    assert "compare_contractor_claim" not in [t.name for t in REGISTRY.available_for(what_if, ENGINE_TOOLS)]
    blocked = REGISTRY.dispatch(what_if, "compare_contractor_claim", "{}", agent="cost")
    assert not blocked.ok and "not available in this run" in blocked.error
    assert REGISTRY.dispatch(contractor, "compare_contractor_claim", "{}", agent="cost").ok


# --- input validation ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tool", "args", "message"),
    [
        ("search_boq", {"query": "paving", "top_k": 50}, "Invalid arguments"),
        ("search_boq", {}, "Invalid arguments"),
        ("price_change", {"change_type": "road_widening"}, "Invalid arguments"),
        ("get_boq_item", {"code": "Z-99"}, "Unknown BOQ code"),
        ("get_clause", {"clause_id": "77.1"}, "Unknown clause"),
        ("evaluate_option", {"extra_crews_on": ["A100"]}, "Not eligible"),
        ("check_notice", {"event_date": "2026-11-04", "notice_date": "2026-11-02"}, "before"),
        ("check_notice", {"event_date": "not a date", "notice_date": "2026-11-02"}, "Invalid arguments"),
        ("read_blackboard", {"section": "secrets"}, "Invalid arguments"),
        ("no_such_tool", {}, "Unknown tool"),
    ],
)
def test_invalid_inputs_return_errors(tool: str, args: dict, message: str) -> None:
    session = make_session("wall_height", mode="contractor_pvr")
    outcome = REGISTRY.dispatch(session, tool, json.dumps(args), agent="cost")
    assert not outcome.ok
    assert message in outcome.error
    assert "error" in json.loads(outcome.model_content)
    assert outcome.facts == []


def test_malformed_json_arguments() -> None:
    outcome = REGISTRY.dispatch(make_session("wall_height"), "search_boq", "{not json", agent="cost")
    assert not outcome.ok and "not valid JSON" in outcome.error


def test_tool_outside_allowed_list_is_refused() -> None:
    outcome = REGISTRY.dispatch(make_session("wall_height"), "search_options", "{}", agent="cost",
                                allowed=["price_change", "post_message"])
    assert not outcome.ok and "not available to cost" in outcome.error


# --- fact registration --------------------------------------------------------------------------------

CALLS = [
    ("get_change_request", {}), ("compare_drawing_revisions", {}), ("quantify_change", {}), ("price_change", {}),
    ("added_duration", {}), ("run_cpm", {}), ("evaluate_option", {"extra_crews_on": ["A340"]}),
    ("search_options", {}), ("check_buffer", {"option_id": "OPT-NONE"}), ("search_boq", {"query": "plaster"}),
    ("search_contract", {"query": "extension of time"}), ("get_clause", {"clause_id": "8.5"}),
    ("check_notice", {"event_date": "2026-11-02", "notice_date": "2026-11-04"}),
    ("compare_contractor_claim", {}),
]


@pytest.mark.parametrize(("tool", "args"), CALLS, ids=[c[0] for c in CALLS])
def test_every_number_in_a_result_has_a_fact(tool: str, args: dict) -> None:
    session = make_session("wall_height", mode="contractor_pvr")
    outcome = REGISTRY.dispatch(session, tool, args, agent="cost")
    assert outcome.ok, outcome.error
    leaves = numeric_leaves(outcome.result)
    by_path = {f.path: f for f in outcome.facts}
    for path, value in leaves:
        fact = by_path[path]
        assert fact.value == value and fact.tool == tool and fact.tool_call_id == outcome.tool_call_id
        assert fact.fact_id in session.facts
    # The model sees every fact id next to its value.
    shown = set(re.findall(r"\[(F-\d{4})\]", outcome.model_content))
    assert shown == {f.fact_id for f in outcome.facts}
    assert len(session.bus.of_type("fact.registered")) == len(outcome.facts)


def test_fact_units_and_lookup() -> None:
    session = make_session("wall_height")
    outcome = REGISTRY.dispatch(session, "price_change", {}, agent="cost")
    direct = session.facts.find("price_change", "direct_cost_aed")[0]
    assert direct.unit == "AED" and direct.value == outcome.result["direct_cost_aed"]
    delta = session.facts.find("price_change", "lines[0].delta")[0]
    assert delta.unit == "m2"
    timing = REGISTRY.dispatch(session, "run_cpm", {"include_change_durations": False}, agent="time")
    assert timing.result["completion_working_day"] == session.data.project.contract_completion_working_day
    assert session.facts.find("run_cpm", "completion_working_day")[0].unit == "wd"
    assert session.facts.find("run_cpm", "completion_date")[0].unit == "date"


def test_infer_unit_rules() -> None:
    assert infer_unit("total_cost_aed", {}) == "AED"
    assert infer_unit("delay_working_days", {}) == "wd"
    assert infer_unit("calendar_days", {}) == "cd"
    assert infer_unit("delta", {"unit": "m3"}) == "m3"
    assert infer_unit("value", {"label": "New wall height (m)"}) == "m"
    assert infer_unit("score", {}) == ""


def test_units_match() -> None:
    assert units_match("AED/m2", "AED") and units_match("aed per working day", "AED")
    assert units_match("working days", "wd") and units_match("days", "wd") and units_match("days", "cd")
    assert not units_match("wd", "cd") and not units_match("calendar days", "wd")
    assert units_match("", "date") and units_match("", "AED")  # no unit stated: nothing to contradict
    assert not units_match("m", "m2") and not units_match("AED", "wd")
    assert units_match("square metres", "m2") and units_match("anything", "")


def test_check_notice_only_with_a_contractor_claim() -> None:
    what_if = make_session("paving_area")
    outcome = REGISTRY.dispatch(what_if, "check_notice", {"event_date": "2026-11-02", "notice_date": "2026-11-04"},
                                agent="intake")
    assert not outcome.ok and "not available in this run" in outcome.error


def test_check_claim() -> None:
    facts = FactRegistry()
    _, new = facts.register_result("T-0001", "price_change", {"direct_cost_aed": 1234.5, "date": "2027-01-02"})
    cost_id, date_id = new[0].fact_id, new[1].fact_id
    assert facts.check_claim(cost_id, 1234.5, "AED") is None
    assert facts.check_claim(cost_id, "1234.509", "aed") is None
    assert "does not match" in (facts.check_claim(cost_id, 1300, "AED") or "")
    assert "unit" in (facts.check_claim(cost_id, 1234.5, "wd") or "")
    assert "does not exist" in (facts.check_claim("F-9999", 1, "AED") or "")
    assert facts.check_claim(date_id, "2027-01-02", "date") is None


def test_post_message_records_envelope() -> None:
    session = make_session("paving_area")
    outcome = REGISTRY.dispatch(session, "post_message", {
        "to": "all", "intent": "ASSESS", "content": "Assessment posted.", "claims": [], "stance": None,
    }, agent="cost")
    assert outcome.ok
    message = session.messages[0]
    assert message.from_agent == "cost" and message.message_id == outcome.result["message_id"]
    dumped = message.model_dump(mode="json")
    assert dumped["from"] == "cost" and dumped["run_id"] == session.run_id
    bad = REGISTRY.dispatch(session, "post_message", {"to": "boss", "intent": "ASSESS", "content": "x"}, agent="cost")
    assert not bad.ok and "'to' must be one of" in bad.error
    bad_intent = REGISTRY.dispatch(session, "post_message", {"to": "all", "intent": "SHOUT", "content": "x"},
                                   agent="cost")
    assert not bad_intent.ok


def test_stance_and_proposals_must_be_evaluated_options() -> None:
    session = make_session("paving_area")

    def post(**fields: object) -> str:
        args = {"to": "all", "intent": "ASSESS", "content": "x", **fields}
        outcome = REGISTRY.dispatch(session, "post_message", args, agent="cost")
        return "" if outcome.ok else outcome.error

    assert "OPT-UNKNOWN was not evaluated" in post(stance="OPT-UNKNOWN")
    assert "none yet" in post(proposals=["OPT-NONE"])
    assert not session.messages  # a refused message is not posted
    assert REGISTRY.dispatch(session, "evaluate_option", {"extra_crews_on": []}, agent="time").ok
    assert post(stance="OPT-NONE", proposals=["OPT-NONE"]) == ""
    assert "OPT-A420 was not evaluated" in post(stance="OPT-A420")


def test_post_message_guards() -> None:
    session = make_session("paving_area")

    def post(agent: str, **fields: object) -> str:
        args = {"to": "all", "intent": "ASSESS", "content": "x", **fields}
        outcome = REGISTRY.dispatch(session, "post_message", args, agent=agent)
        return "" if outcome.ok else outcome.error

    assert post("cost", claims=None, proposals=None, stance="") == ""
    assert "option ids" in post("contract", proposals=["ACT-001"])
    assert "stance must be an option id" in post("contract", stance="create_task")
    assert "Only the verifier" in post("commercial", intent="VERIFY")
    assert "Only the moderator" in post("cost", intent="SUMMARISE")
    assert post("verifier", intent="VERIFY", to="cost") == ""
