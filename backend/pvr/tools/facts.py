"""Fact registry: every number (and date) in every tool result gets a fact id.

The model sees tool results with each value written as `"<value> [F-0007]"`, so it
can cite the fact. The UI can open any fact and show the tool call that produced it.
"""

from __future__ import annotations

import re
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
    "day": "days", "days": "days", "calendar days": "days", "calendar day": "days",
    "m2": "m2", "m²": "m2", "sq m": "m2", "square metres": "m2",
    "m3": "m3", "m³": "m3", "cubic metres": "m3",
    "m": "m", "metre": "m", "metres": "m", "meter": "m", "meters": "m",
    "%": "%", "percent": "%",
    "date": "date",
}


def normalise_unit(unit: str) -> str:
    """Canonical unit name, so `working days` matches `wd` and `m²` matches `m2`."""
    key = unit.strip().lower()
    return UNIT_ALIASES.get(key, key)


class Fact(BaseModel):
    fact_id: str
    tool_call_id: str
    tool: str
    path: str
    value: float | str
    unit: str


def infer_unit(key: str, siblings: dict[str, Any]) -> str:
    """Unit of a value from its key name, or from a sibling `unit` or `label` field."""
    if key.endswith("_aed"):
        return "AED"
    if key.endswith("_percent"):
        return "%"
    if "calendar" in key or key == "limit_days":
        return "days"
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
        return [f for f in self._facts.values() if f.tool == tool and f.path == path]

    def _register(self, tool_call_id: str, tool: str, path: str, value: float | str, unit: str) -> Fact:
        self._count += 1
        fact = Fact(fact_id=f"F-{self._count:04d}", tool_call_id=tool_call_id, tool=tool,
                    path=path, value=value, unit=unit)
        self._facts[fact.fact_id] = fact
        return fact

    def register_result(self, tool_call_id: str, tool: str, result: Any) -> tuple[Any, list[Fact]]:
        """Register every number and date in a JSON result.

        Returns the annotated copy for the model (values as `"<value> [F-0001]"`) and the new facts.
        """
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
                return node
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
            if abs(number - fact.value) > 0.01:
                return f"value {value} does not match {fact_id} ({fact.value})"
        if fact.unit and normalise_unit(unit) != fact.unit:
            return f"unit '{unit}' does not match {fact_id} ({fact.unit})"
        return None
