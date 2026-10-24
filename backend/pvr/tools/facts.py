"""Fact registry: every number (and date) in every tool result gets a fact id.

The model sees tool results with each value written as `"<value> [F-0007]"`, so it
can cite the fact. The UI can open any fact and show the tool call that produced it.
"""

from __future__ import annotations

import re
import threading
from typing import Any

from pydantic import BaseModel

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_LABEL_UNIT = re.compile(r"\(([^)]+)\)\s*$")

_WORKING_DAY_KEYS = {
    "ES", "EF", "LS", "LF", "TF", "duration", "baseline_duration", "new_duration", "added_days",
    "duration_before", "duration_after", "lag",
}
_QUANTITY_KEYS = {
    "old", "new", "delta", "quantity", "claimed_quantity", "assessed_quantity", "quantity_difference",
    "claimed", "assessed", "difference",
}
_PARAMETER_KEYS = {"value", "default", "min", "max", "step"}

UNIT_ALIASES = {
    "aed": "AED", "dirham": "AED", "dirhams": "AED",
    "wd": "wd", "working day": "wd", "working days": "wd", "working_days": "wd", "days (working)": "wd",
    "day": "days", "days": "days",
    "cd": "cd", "calendar days": "cd", "calendar day": "cd",
    "m2": "m2", "m²": "m2", "sq m": "m2", "square metres": "m2",
    "m3": "m3", "m³": "m3", "cubic metres": "m3",
    "m": "m", "metre": "m", "metres": "m", "meter": "m", "meters": "m",
    "%": "%", "percent": "%",
    "date": "date",
}


def normalise_unit(unit: str) -> str:
    """Canonical unit name, so `working days` matches `wd` and `m²` matches `m2`.
    Money with a per-unit suffix (`AED/m2`, `AED per working day`) counts as AED."""
    key = unit.strip().lower()
    if key.startswith("aed"):
        return "AED"
    return UNIT_ALIASES.get(key, key)


def units_match(claim_unit: str, fact_unit: str) -> bool:
    """True when a claim's unit is compatible with its fact's unit.

    Plain `days` is accepted for working (`wd`) or calendar (`cd`) days, but `wd` and `cd` differ.
    A claim without a unit states no unit, so it cannot contradict one. A fact without a unit
    accepts any unit.
    """
    claim = normalise_unit(claim_unit)
    if not fact_unit or not claim or claim == fact_unit:
        return True
    return claim == "days" and fact_unit in ("wd", "cd")


class Fact(BaseModel):
    fact_id: str
    tool_call_id: str
    tool: str
    path: str
    value: float | str
    unit: str


# Numbers inside text (clause text, descriptions, instructions). Codes such as B-04-010, L-201 or A320
# are not numbers: a digit preceded by a letter, digit, dot, hyphen or slash is skipped.
_TEXT_NUMBER = re.compile(r"(?<![\w.\-/])\d[\d,]*(?:\.\d+)?(?![\d.]*\d)")
_TEXT_UNIT_AFTER = (
    (re.compile(r"\s*(%|per ?cent)", re.I), "%"),
    (re.compile(r"\s*working days?\b", re.I), "wd"),
    (re.compile(r"\s*calendar days?\b", re.I), "cd"),
    (re.compile(r"\s*days?\b", re.I), "days"),
    (re.compile(r"\s*(m2\b|m²)"), "m2"),
    (re.compile(r"\s*(m3\b|m³)"), "m3"),
    (re.compile(r"\s*mm\b"), "mm"),
    (re.compile(r"\s*m\b"), "m"),
)
# String fields that hold identifiers, not text.
_ID_KEYS = {"clause", "code", "id", "ref", "drawing", "revision", "bill", "section", "matched_code", "status"}


def text_numbers(text: str) -> list[tuple[int, int, float, str]]:
    """(start, end, value, unit) for each number in free text. Clause numbers (`Clause 13`) are skipped."""
    found = []
    for match in _TEXT_NUMBER.finditer(text):
        raw = match.group().rstrip(",")
        end = match.start() + len(raw)
        before = text[max(0, match.start() - 9):match.start()].lower().rstrip()
        if before.endswith(("clause", "clauses")) or not raw:
            continue
        unit = "AED" if before.endswith("aed") else ""
        if not unit:
            for pattern, name in _TEXT_UNIT_AFTER:
                if pattern.match(text, end):
                    unit = name
                    break
        found.append((match.start(), end, float(raw.replace(",", "")), unit))
    return found


def _is_id_key(key: str) -> bool:
    return key in _ID_KEYS or key.endswith(("_id", "_ref", "_ids"))


def infer_unit(key: str, siblings: dict[str, Any]) -> str:
    """Unit of a value from its key name, or from a sibling `unit` or `label` field."""
    if key.endswith("_aed"):
        return "AED"
    if key.endswith("_percent"):
        return "%"
    if "calendar" in key or key == "limit_days":
        return "cd"
    if key in _WORKING_DAY_KEYS or key.endswith(("_days", "_working_day", "_working_days")):
        return "wd"
    if key == "crew_days":
        return "crew-days"
    if key in _QUANTITY_KEYS and isinstance(siblings.get("unit"), str):
        return normalise_unit(siblings["unit"])
    if key in _PARAMETER_KEYS and isinstance(siblings.get("label"), str):
        match = _LABEL_UNIT.search(siblings["label"])
        if match:
            return normalise_unit(match.group(1))
    for suffix, unit in (("_m2", "m2"), ("_m3", "m3"), ("_m", "m")):
        if key.endswith(suffix):
            return unit
    return ""


class FactRegistry:
    """All facts of one run, in registration order."""

    def __init__(self) -> None:
        self._facts: dict[str, Fact] = {}
        self._count = 0
        self._lock = threading.RLock()

    def __contains__(self, fact_id: object) -> bool:
        return fact_id in self._facts

    def __len__(self) -> int:
        return len(self._facts)

    def get(self, fact_id: str) -> Fact | None:
        return self._facts.get(fact_id)

    def all(self) -> list[Fact]:
        return list(self._facts.values())

    def find(self, tool: str, path: str) -> list[Fact]:
        """Facts from a tool at a path (latest last)."""
        with self._lock:
            return [f for f in self._facts.values() if f.tool == tool and f.path == path]

    def with_value(self, value: float | str, limit: int = 3) -> list[Fact]:
        """The most recent facts holding this value (numbers compared by absolute value within 0.01)."""
        with self._lock:
            facts = list(self._facts.values())
        if isinstance(value, str):
            hits = [f for f in facts if f.value == value]
        else:
            hits = [f for f in facts if isinstance(f.value, float) and abs(abs(f.value) - abs(value)) <= 0.01]
        return hits[-limit:]

    def _register(self, tool_call_id: str, tool: str, path: str, value: float | str, unit: str) -> Fact:
        self._count += 1
        fact = Fact(fact_id=f"F-{self._count:04d}", tool_call_id=tool_call_id, tool=tool,
                    path=path, value=value, unit=unit)
        self._facts[fact.fact_id] = fact
        return fact

    def register_result(self, tool_call_id: str, tool: str, result: Any) -> tuple[Any, list[Fact]]:
        """Register every number and date in a JSON result, including numbers inside text.

        Returns the annotated copy for the model (values as `"<value> [F-0001]"`) and the new facts.
        """
        with self._lock:
            return self._register_result(tool_call_id, tool, result)

    def _register_result(self, tool_call_id: str, tool: str, result: Any) -> tuple[Any, list[Fact]]:
        new: list[Fact] = []

        def walk(node: Any, path: str, key: str, siblings: dict[str, Any]) -> Any:
            if isinstance(node, bool) or node is None:
                return node
            if isinstance(node, (int, float)):
                fact = self._register(tool_call_id, tool, path, float(node), infer_unit(key, siblings))
                new.append(fact)
                return f"{node} [{fact.fact_id}]"
            if isinstance(node, str):
                if _DATE.match(node):
                    fact = self._register(tool_call_id, tool, path, node, "date")
                    new.append(fact)
                    return f"{node} [{fact.fact_id}]"
                if _is_id_key(key):
                    return node
                out, last = [], 0
                for i, (start, end, value, unit) in enumerate(text_numbers(node)):
                    fact = self._register(tool_call_id, tool, f"{path}#{i}", value, unit)
                    new.append(fact)
                    out.append(node[last:end] + f" [{fact.fact_id}]")
                    last = end
                return "".join(out) + node[last:]
            if isinstance(node, dict):
                return {k: walk(v, f"{path}.{k}" if path else k, k, node) for k, v in node.items()}
            if isinstance(node, list):
                return [walk(v, f"{path}[{i}]", key, siblings) for i, v in enumerate(node)]
            return node

        annotated = walk(result, "", "", {})
        return annotated, new

    def check_claim(self, fact_id: str, value: float | str, unit: str) -> str | None:
        """None if the claim matches its fact (value within 0.01, same unit), else the problem."""
        fact = self._facts.get(fact_id)
        if fact is None:
            return f"fact {fact_id} does not exist"
        if isinstance(fact.value, str):
            if str(value).strip() != fact.value:
                return f"value {value} does not match {fact_id} ({fact.value})"
        else:
            try:
                number = float(value)
            except (TypeError, ValueError):
                return f"value {value} is not a number; {fact_id} is {fact.value}"
            # Magnitudes are compared: "contingency left -4,929" and "4,929 over the contingency" both
            # state the same fact; the words carry the direction.
            if abs(abs(number) - abs(fact.value)) > 0.01:
                return f"value {value} does not match {fact_id} ({fact.value})"
        if not units_match(unit, fact.unit):
            return f"unit '{unit}' does not match {fact_id} ({fact.unit})"
        return None
