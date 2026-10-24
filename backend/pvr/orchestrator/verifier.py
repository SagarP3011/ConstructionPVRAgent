"""Deterministic checks the Verifier runs on every agent message (SPEC 10.4).

1. Every claim cites an existing fact; value within 0.01 and unit match.
2. Every number in the content is covered by a claim (option ids, clause ids, BOQ codes, activity
   ids, other codes, product sizes in mm and the counts 0 and 1 are ignored; dates must be covered
   by date claims). Inline citations ("AED 1234.5 [F-0012]") become claims in post_message.
3. Every clause referenced exists in the contract.
4. Every option id referenced was evaluated in this run.
Plus stage rules: debate messages are addressed to one agent with a stance, and the Moderator's
summary presents the Pareto options only.
"""

from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel, Field

from pvr.engines import options as options_engine
from pvr.engines.contract import clause_exists
from pvr.models import AgentMessage, Claim
from pvr.orchestrator.context import RunSession
from pvr.tools.facts import units_match

_MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
_WEEKDAY = r"(?:(?:mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)[a-z]*,?\s+)?"
_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DMY_DATE = re.compile(_WEEKDAY + r"\b(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?,?\s+(\d{4})\b",
                       re.I)
_MDY_DATE = re.compile(_WEEKDAY + r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})\b",
                       re.I)
OPTION_ID = re.compile(r"\bOPT-[A-Z0-9]+(?:-[A-Z0-9]+)*")
_CLAUSE_REF = re.compile(r"\bclauses?\s+(\d+(?:\.\d+)*(?:\s*(?:,|and|or|&|/)\s*\d+(?:\.\d+)*)*)", re.I)
# Codes and ids: B-04-010, L-201, VI-017, PVR-023, F-0012, M-0003, A320, R-101, Rev C ...
_CODES = re.compile(r"\b[A-Za-z]+(?:-[A-Za-z0-9]+)+\b|\b[A-Za-z]+\d+[A-Za-z0-9]*\b")
_NUMBER = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")
# Product sizes in millimetres come from item descriptions (for example "blockwork, 200 mm"); the
# engines never compute them, so they are part of the item's name rather than a figure to verify.
_MILLIMETRES = re.compile(r"(?<![\w.])\d+(?:\.\d+)?\s*mm\b")


# 0 and 1 written as digits are almost always counts or labels ("1 extra crew", "option 1"), not
# figures from a tool. They are the only numbers allowed without a claim.
COUNT_WORDS = {0.0, 1.0}


class VerificationResult(BaseModel):
    status: str  # "pass" or "fail"
    issues: list[str] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.status == "pass"


def extract_dates(text: str) -> tuple[list[str], str]:
    """ISO dates mentioned in the text, and the text with those dates removed."""
    found: list[str] = []

    def iso(y: int, m: int, d: int) -> str:
        try:
            return date(y, m, d).isoformat()
        except ValueError:
            return f"{y:04d}-{m:02d}-{d:02d}"

    def sub_iso(m: re.Match[str]) -> str:
        found.append(iso(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        return " "

    def sub_dmy(m: re.Match[str]) -> str:
        found.append(iso(int(m.group(3)), _MONTHS[m.group(2).lower()[:3]], int(m.group(1))))
        return " "

    def sub_mdy(m: re.Match[str]) -> str:
        found.append(iso(int(m.group(3)), _MONTHS[m.group(1).lower()[:3]], int(m.group(2))))
        return " "

    text = _ISO_DATE.sub(sub_iso, text)
    text = _DMY_DATE.sub(sub_dmy, text)
    text = _MDY_DATE.sub(sub_mdy, text)
    return found, text


def clause_refs(text: str) -> list[str]:
    """Clause numbers referenced as `clause 13.3`, `clauses 8.4 and 8.5`."""
    refs: list[str] = []
    for match in _CLAUSE_REF.finditer(text):
        refs += re.findall(r"\d+(?:\.\d+)*", match.group(1))
    return refs


_FACT_CITATION = re.compile(r"\[\s*F-\d{4,}\s*\]")


def mask_non_values(text: str) -> str:
    """The text with fact citations, clause references, option ids, codes and mm sizes blanked out
    (same length, so positions still line up). What is left are values: numbers and dates."""
    def blank(m: re.Match[str]) -> str:
        return " " * len(m.group())

    for pattern in (_FACT_CITATION, _CLAUSE_REF, _MILLIMETRES, OPTION_ID, _CODES):
        text = pattern.sub(blank, text)
    return text


def bare_numbers(text: str) -> list[tuple[str, float]]:
    """Numbers in text after removing dates, clause references, option ids and other codes."""
    _, text = extract_dates(text)
    text = _CLAUSE_REF.sub(" ", text)
    text = _MILLIMETRES.sub(" ", text)
    text = OPTION_ID.sub(" ", text)
    text = _CODES.sub(" ", text)
    found = []
    for match in _NUMBER.finditer(text):
        raw = match.group().rstrip(",")
        if raw:
            found.append((raw, float(raw.replace(",", ""))))
    return found


def verify_message(session: RunSession, message: AgentMessage) -> VerificationResult:
    """Run every deterministic check on one message."""
    issues: list[str] = []
    facts = session.facts

    # 1. Claims match their facts.
    for claim in message.claims:
        problem = facts.check_claim(claim.fact_id, claim.value, claim.unit)
        if problem:
            issues.append(f"Claim '{claim.label}': {problem}{_claim_hint(session, claim)}")

    # 2. Every number and date in the content is covered by a claim.
    numeric_claims = [float(c.value) for c in message.claims if _is_number(c.value)]
    date_claims = {str(c.value).strip() for c in message.claims if not _is_number(c.value)}
    dates, _ = extract_dates(message.content)
    for d in dates:
        if d not in date_claims:
            issues.append(f"Date {d} in the text has no claim with a fact id{_hint(session, d)}")
    for raw, value in bare_numbers(message.content):
        if value in COUNT_WORDS or ("." in raw and clause_exists(raw, session.data)):
            continue  # a count, or a clause number written without the word "clause"
        if not any(abs(abs(value) - abs(v)) <= 0.01 for v in numeric_claims):
            issues.append(f"Number {raw} in the text has no claim with a fact id{_hint(session, value)}")

    # 3. Clauses exist (a clause group such as "clause 13" counts when 13.1, 13.3 ... exist).
    for ref in clause_refs(message.content):
        if not clause_exists(ref, session.data) and \
                not any(c.clause.startswith(ref + ".") for c in session.data.contract.clauses):
            issues.append(f"Clause {ref} does not exist in the contract")

    # 4. Options were evaluated in this run.
    referenced = set(OPTION_ID.findall(message.content)) | set(message.proposals)
    if message.stance:
        referenced.add(message.stance)
    for option_id in sorted(referenced):
        if option_id not in session.evaluated_options:
            issues.append(f"Option {option_id} was not evaluated in this run")

    issues += stage_rule_issues(session, message)
    return VerificationResult(status="fail" if issues else "pass", issues=issues)


DEBATE_INTENTS = ("PROPOSE", "CHALLENGE", "AGREE")
MAX_PRESENTED_OPTIONS = 3


def stage_rule_issues(session: RunSession, message: AgentMessage) -> list[str]:
    """Rules of the stage the message belongs to."""
    issues: list[str] = []
    if message.stage == "debate" and message.intent != "ANSWER":
        if message.intent not in DEBATE_INTENTS:
            issues.append(f"In the debate, intent must be one of {', '.join(DEBATE_INTENTS)}")
        if message.to in ("all", message.from_agent):
            issues.append("In the debate, address one specific other agent")
        if not message.stance:
            issues.append("In the debate, give your stance (your preferred option id)")
    if message.stage == "synthesis" and message.intent == "SUMMARISE":
        search = options_engine.search_options(session.ctx, session.data)
        pareto = search.pareto_option_ids[:MAX_PRESENTED_OPTIONS]
        presented = message.proposals
        if not presented:
            issues.append("List the options you present in proposals")
        if len(presented) > MAX_PRESENTED_OPTIONS:
            issues.append(f"Present at most {MAX_PRESENTED_OPTIONS} options")
        by_id = {o.option_id: o for o in search.options}
        for option_id in presented:
            if option_id in by_id and option_id not in search.pareto_option_ids:
                better = next(o.option_id for o in search.options
                              if o.option_id in search.pareto_option_ids
                              and o.total_cost_aed <= by_id[option_id].total_cost_aed
                              and o.delay_working_days <= by_id[option_id].delay_working_days)
                issues.append(f"Option {option_id} is beaten on both cost and delay by {better}")
        for option_id in pareto:
            if option_id not in presented:
                issues.append(f"Option {option_id} is not beaten on both cost and delay by any other option "
                              "but is not presented")
    return issues


def _hint(session: RunSession, value: float | str) -> str:
    """Where the value can be cited from, or a note that no tool produced it."""
    facts = session.facts.with_value(value)
    if not facts:
        return " (no tool result in this run has this value: remove it or call a tool that gives it)"
    return " (facts with this value: " + ", ".join(f"{f.fact_id} {f.tool}.{f.path}" for f in facts) + ")"


def _claim_hint(session: RunSession, claim: Claim) -> str:
    """Facts that hold the claimed value with a compatible unit, so the author can cite the right one."""
    value: float | str = float(claim.value) if _is_number(claim.value) else str(claim.value)
    matches = [f for f in session.facts.with_value(value, limit=20)
               if f.fact_id != claim.fact_id and units_match(claim.unit, f.unit)][-3:]
    if not matches:
        return " (no tool result in this run has this value with this unit)"
    return " (facts with this value: " + ", ".join(f"{f.fact_id} {f.tool}.{f.path}" for f in matches) + ")"


def _is_number(value: object) -> bool:
    if isinstance(value, (int, float)):
        return True
    try:
        float(str(value))
        return True
    except ValueError:
        return False
