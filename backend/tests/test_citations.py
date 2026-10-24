"""Inline fact citations become claims and are removed from the text."""

from __future__ import annotations

from conftest import make_session
from pvr.orchestrator.verifier import verify_message
from pvr.tools.citations import extract_citations, merge_claims
from pvr.tools.facts import FactRegistry
from pvr.tools.registry import REGISTRY
from pvr.models import Claim


def registry_with(values: dict) -> tuple[FactRegistry, dict[str, str]]:
    facts = FactRegistry()
    _, new = facts.register_result("T-0001", "tool", values)
    return facts, {f.path: f.fact_id for f in new}


def test_citations_become_claims_and_are_removed() -> None:
    facts, ids = registry_with({"total_cost_aed": 63529.0, "completion_date": "2027-02-12", "delay_working_days": 8})
    text = (f"Total AED 63,529 [{ids['total_cost_aed']}], completion 12 Feb 2027 [{ids['completion_date']}] "
            f"after 8 [{ids['delay_working_days']}] working days of delay.")
    clean, claims = extract_citations(text, facts)
    assert clean == "Total AED 63,529, completion 12 Feb 2027 after 8 working days of delay."
    assert [(c.value, c.unit, c.fact_id) for c in claims] == [
        (63529.0, "AED", ids["total_cost_aed"]), ("2027-02-12", "date", ids["completion_date"]),
        (8.0, "wd", ids["delay_working_days"])]
    assert claims[0].label == "total cost aed"


def test_citation_without_a_number_is_dropped_and_wrong_number_is_kept() -> None:
    facts, ids = registry_with({"total_cost_aed": 100.0})
    clean, claims = extract_citations(f"The total [{ids['total_cost_aed']}] is fine.", facts)
    assert clean == "The total is fine." and claims == []
    _, claims = extract_citations(f"The total is AED 120 [{ids['total_cost_aed']}].", facts)
    assert claims[0].value == 120.0  # the number as written, so the Verifier can catch the mismatch


def test_citation_pairs_only_with_the_value_right_before_it() -> None:
    facts, ids = registry_with({"contingency_remaining_aed": 28200.0, "delay_working_days": 0, "limit_days": 28})
    text = (f"Contingency AED 28,200 [{ids['contingency_remaining_aed']}] with no delay "
            f"[{ids['delay_working_days']}]; notice within 28 days under clause 20.1 [{ids['limit_days']}].")
    clean, claims = extract_citations(text, facts)
    assert [(c.value, c.fact_id) for c in claims] == [(28200.0, ids["contingency_remaining_aed"])]
    assert "[F-" not in clean


def test_merge_claims_keeps_explicit_first() -> None:
    explicit = [Claim(label="a", value=1.0, unit="", fact_id="F-0001")]
    inline = [Claim(label="a", value=1.0, unit="", fact_id="F-0001"), Claim(label="b", value=2.0, fact_id="F-0002")]
    assert [c.fact_id for c in merge_claims(explicit, inline)] == ["F-0001", "F-0002"]


def test_post_message_with_inline_citations_verifies() -> None:
    session = make_session("paving_area")
    REGISTRY.dispatch(session, "price_change", {}, agent="cost")
    fact = session.facts.find("price_change", "direct_cost_aed")[0]
    outcome = REGISTRY.dispatch(session, "post_message", {
        "to": "all", "intent": "ASSESS", "content": f"Direct cost AED {fact.value:,.2f} [{fact.fact_id}] (clause 13.3)."
    }, agent="cost")
    assert outcome.ok
    message = session.messages[-1]
    assert "[F-" not in message.content and message.claims[0].fact_id == fact.fact_id
    assert verify_message(session, message).passed


def test_wrong_inline_number_fails_verification() -> None:
    session = make_session("paving_area")
    REGISTRY.dispatch(session, "price_change", {}, agent="cost")
    fact = session.facts.find("price_change", "direct_cost_aed")[0]
    REGISTRY.dispatch(session, "post_message", {
        "to": "all", "intent": "ASSESS", "content": f"Direct cost AED 99,999 [{fact.fact_id}]."}, agent="cost")
    result = verify_message(session, session.messages[-1])
    assert not result.passed and "does not match" in result.issues[0]
