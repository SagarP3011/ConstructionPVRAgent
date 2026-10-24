"""Agent definitions: role, goal, allowed tools and model tier (SPEC 9).

Phase 2 defines the Cost agent; the other six agents are added in Phase 3.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

PROMPTS_DIR = Path(__file__).parent / "prompts"

AGENT_NAMES: list[str] = ["moderator", "intake", "contract", "cost", "time", "commercial", "verifier"]


@dataclass(frozen=True)
class AgentSpec:
    name: str
    title: str
    goal: str
    tools: tuple[str, ...]
    model_tier: Literal["main", "light"] = "main"

    @property
    def prompt_file(self) -> Path:
        return PROMPTS_DIR / f"{self.name}.md"


COST = AgentSpec(
    name="cost",
    title="Cost agent (quantity surveyor)",
    goal="Quantify and price the change at contract rates, and argue for value for money.",
    tools=("quantify_change", "search_boq", "get_boq_item", "price_change", "compare_contractor_claim",
           "check_buffer", "ask_agent", "read_blackboard", "post_message"),
)

ROSTER: dict[str, AgentSpec] = {COST.name: COST}


def get_agent(name: str) -> AgentSpec:
    try:
        return ROSTER[name]
    except KeyError:
        raise KeyError(f"Unknown agent: {name}. Defined: {', '.join(ROSTER)}") from None
