"""Inline fact citations in message text.

Agents may cite a fact right after a number, the way tool results show values:
"a direct cost of AED 1234.5 [F-0012]". `post_message` turns each citation into a claim (with the
number as written in the text, so the Verifier still compares text against fact) and removes the
fact id from the text people read.
"""

from __future__ import annotations

import re

from pvr.models import Claim
from pvr.orchestrator.verifier import extract_dates, mask_non_values
from pvr.tools.facts import FactRegistry

_CITATION = re.compile(r"\s*\[\s*(F-\d{4,})\s*\]")
_MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"
_VALUE = re.compile(
    r"(?P<iso>\b\d{4}-\d{2}-\d{2}\b)"
    rf"|(?P<dmy>\b\d{{1,2}}\s+(?:{_MONTHS})[a-z]*\.?,?\s+\d{{4}}\b)"
    r"|(?P<num>(?<![\w.\-])-?\d[\d,]*(?:\.\d+)?)",
    re.I,
)
MAX_GAP = 40  # characters searched before a citation
# What may stand between a value and its citation: spaces, punctuation and a unit, nothing else.
_UNIT_GAP = re.compile(
    r"^[\s,.;:)]*(?:(?:aed|wd|cd|working\s+days?|calendar\s+days?|days?|m2|m3|m²|m³|mm|m|%|per\s*cent|percent|"
    r"square\s+metres?|cubic\s+metres?|metres?)\b\.?)?[\s,.;:)]*$|^%[\s,.;:)]*$",
    re.I,
)


def _label(path: str) -> str:
    last = path.split(".")[-1]
    last = re.sub(r"\[\d+\]|#\d+", "", last)
    return last.replace("_", " ").strip() or path


def _as_value(match: re.Match[str]) -> float | str:
    if match.group("iso"):
        return match.group("iso")
    if match.group("dmy"):
        dates, _ = extract_dates(match.group("dmy"))
        return dates[0] if dates else match.group("dmy")
    return float(match.group("num").rstrip(",").replace(",", ""))


def extract_citations(content: str, facts: FactRegistry) -> tuple[str, list[Claim]]:
    """Clean text and the claims made by inline citations. Each citation is paired with the value
    (number or date) directly before it, with at most a unit in between ("AED 1,234 [F-0012]",
    "8 working days [F-0031]"). Clause numbers, option ids and codes are ignored. A citation with no
    value right before it (for example after "no delay") makes no claim."""
    masked = mask_non_values(content)
    claims: list[Claim] = []
    for cite in _CITATION.finditer(content):
        fact_id = cite.group(1)
        values = list(_VALUE.finditer(masked, max(0, cite.start() - MAX_GAP), cite.start()))
        if not values or not _UNIT_GAP.match(masked[values[-1].end():cite.start()]):
            continue
        fact = facts.get(fact_id)
        claims.append(Claim(label=_label(fact.path) if fact else "cited value", value=_as_value(values[-1]),
                            unit=fact.unit if fact else "", fact_id=fact_id))
    return _CITATION.sub("", content), claims


def merge_claims(explicit: list[Claim], inline: list[Claim]) -> list[Claim]:
    """Explicit claims first, then inline ones not already listed (same fact and value)."""
    seen = {(c.fact_id, str(c.value)) for c in explicit}
    return list(explicit) + [c for c in inline if (c.fact_id, str(c.value)) not in seen]
