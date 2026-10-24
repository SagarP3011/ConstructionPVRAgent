"""Verifier checks (SPEC 10.4)."""

from __future__ import annotations

from conftest import make_session
from pvr.ids import now_iso
from pvr.models import AgentMessage, Claim
from pvr.orchestrator.context import RunSession
from pvr.orchestrator.verifier import bare_numbers, clause_refs, extract_dates, verify_message
from pvr.tools.registry import REGISTRY


def priced_session() -> tuple[RunSession, str, float]:
    session = make_session("paving_area")
    REGISTRY.dispatch(session, "price_change", {}, agent="cost")
    REGISTRY.dispatch(session, "search_options", {}, agent="commercial")
    fact = session.facts.find("price_change", "direct_cost_aed")[0]
    return session, fact.fact_id, float(fact.value)


def msg(session: RunSession, content: str, claims: list[Claim] | None = None, **kw: object) -> AgentMessage:
    values: dict[str, object] = dict(message_id="M-0999", run_id=session.run_id, stage="assessment",
                                     from_agent="cost", to="all", intent="ASSESS", content=content,
                                     claims=claims or [], timestamp=now_iso())
    values.update(kw)
    return AgentMessage(**values)  # type: ignore[arg-type]


def test_correct_claim_passes() -> None:
    session, fid, value = priced_session()
    m = msg(session, f"Direct cost is AED {value:,.2f} at BOQ rates (clause 13.3).",
            [Claim(label="direct cost", value=value, unit="AED", fact_id=fid)])
    result = verify_message(session, m)
    assert result.passed, result.issues


def test_wrong_value_fails() -> None:
    session, fid, value = priced_session()
    m = msg(session, f"Direct cost is AED {value + 500:,.0f}.",
            [Claim(label="direct cost", value=value + 500, unit="AED", fact_id=fid)])
    result = verify_message(session, m)
    assert not result.passed and any("does not match" in i for i in result.issues)


def test_wrong_unit_fails() -> None:
    session, fid, value = priced_session()
    m = msg(session, f"It takes {value:g} days.", [Claim(label="x", value=value, unit="wd", fact_id=fid)])
    assert any("unit" in i for i in verify_message(session, m).issues)


def test_missing_fact_fails() -> None:
    session, _, value = priced_session()
    m = msg(session, f"Direct cost is AED {value:g}.", [Claim(label="direct cost", value=value, unit="AED",
                                                             fact_id="F-9999")])
    assert any("does not exist" in i for i in verify_message(session, m).issues)


def test_bare_number_without_claim_fails() -> None:
    session, fid, value = priced_session()
    m = msg(session, f"Direct cost is AED {value:g}, plus 750 for site set-up.",
            [Claim(label="direct cost", value=value, unit="AED", fact_id=fid)])
    issues = verify_message(session, m).issues
    assert len(issues) == 1 and issues[0].startswith("Number 750 in the text has no claim with a fact id")
    assert "no tool result in this run has this value" in issues[0]


def test_uncited_number_hint_names_the_fact() -> None:
    session, fid, value = priced_session()
    issues = verify_message(session, msg(session, f"Direct cost is AED {value:g}.")).issues
    assert len(issues) == 1 and "facts with this value: F-" in issues[0]
    hinted = issues[0].split("facts with this value: ")[1]
    assert all(session.facts.get(fid_.split()[0]).value == value for fid_ in hinted.rstrip(")").split(", "))  # type: ignore[union-attr]
    assert fid in session.facts


def test_uncovered_date_fails_and_covered_date_passes() -> None:
    session = make_session("paving_area")
    REGISTRY.dispatch(session, "run_cpm", {}, agent="time")
    fact = session.facts.find("run_cpm", "completion_date")[0]
    good = msg(session, f"Completion stays on {fact.value}.",
               [Claim(label="completion", value=fact.value, unit="date", fact_id=fact.fact_id)])
    assert verify_message(session, good).passed
    bad = msg(session, "Completion moves to 19 Mar 2027.")
    issues = verify_message(session, bad).issues
    assert len(issues) == 1 and issues[0].startswith("Date 2027-03-19 in the text has no claim with a fact id")


def test_unknown_clause_fails() -> None:
    session, _, _ = priced_session()
    assert verify_message(session, msg(session, "Valued under clause 13.3.")).passed
    issues = verify_message(session, msg(session, "Valued under clauses 13.3 and 13.9.")).issues
    assert issues == ["Clause 13.9 does not exist in the contract"]
    assert verify_message(session, msg(session, "A variation under clause 13.")).passed  # clause group
    assert verify_message(session, msg(session, "See clause 15.")).issues == ["Clause 15 does not exist in the contract"]


def test_unevaluated_option_fails() -> None:
    session = make_session("road_widening")
    REGISTRY.dispatch(session, "evaluate_option", {"extra_crews_on": ["A120"]}, agent="time")
    assert verify_message(session, msg(session, "I prefer OPT-A120.", stance="OPT-A120")).passed
    issues = verify_message(session, msg(session, "OPT-A100 is better.", stance="OPT-A100")).issues
    assert issues == ["Option OPT-A100 was not evaluated in this run"]


def test_codes_and_ids_are_not_numbers() -> None:
    text = ("B-04-010 and A320 on Drawing L-201 Rev C, VI-017, PVR-023, F-0012, M-0004, OPT-A320-A340, "
            "R-02-050 and +200 m2 under clause 8.4")
    assert [raw for raw, _ in bare_numbers(text)] == ["200"]
    assert clause_refs("clauses 8.4, 8.5 and 13.3; Clause 20.1") == ["8.4", "8.5", "13.3", "20.1"]
    assert extract_dates("Fri 12 Feb 2027 and 2027-02-03, or February 5, 2027")[0] == \
        ["2027-02-03", "2027-02-12", "2027-02-05"]


def test_debate_rules() -> None:
    session = make_session("paving_area")
    REGISTRY.dispatch(session, "search_options", {}, agent="commercial")
    bad = msg(session, "Agreed.", stage="debate", intent="ASSESS", to="all")
    issues = verify_message(session, bad).issues
    assert len(issues) == 3
    good = msg(session, "I agree with you.", stage="debate", intent="AGREE", to="time", stance="OPT-NONE")
    assert verify_message(session, good).passed


def test_moderator_must_present_the_pareto_options() -> None:
    session = make_session("wall_height")
    REGISTRY.dispatch(session, "search_options", {}, agent="moderator")
    base = dict(stage="synthesis", intent="SUMMARISE", from_agent="moderator")
    ok = msg(session, "Three options.", proposals=["OPT-A320", "OPT-A340", "OPT-NONE"], **base)
    assert verify_message(session, ok).passed
    dominated = msg(session, "Options.", proposals=["OPT-A330", "OPT-A340", "OPT-NONE"], **base)
    issues = verify_message(session, dominated).issues
    assert any("OPT-A330 is beaten" in i for i in issues) and any("OPT-A320 is not beaten" in i for i in issues)
