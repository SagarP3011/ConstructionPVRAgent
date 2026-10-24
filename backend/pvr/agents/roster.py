"""Agent definitions: role, goal, allowed tools and model tier (SPEC 9).

The roster says what each agent may use; the agent decides what to use and when.
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


INTAKE = AgentSpec(
    name="intake",
    title="Intake agent",
    goal="Understand the change and package the evidence.",
    tools=("get_change_request", "compare_drawing_revisions", "check_notice", "post_message"),
    model_tier="light",
)

CONTRACT = AgentSpec(
    name="contract",
    title="Contract agent",
    goal="Determine eligibility and the contract rules that apply; raise design and new-rate issues.",
    tools=("search_contract", "get_clause", "read_blackboard", "propose_action", "post_message"),
)

COST = AgentSpec(
    name="cost",
    title="Cost agent (quantity surveyor)",
    goal="Quantify and price the change at contract rates, and argue for value for money.",
    tools=("quantify_change", "search_boq", "get_boq_item", "price_change", "compare_contractor_claim",
           "check_buffer", "ask_agent", "read_blackboard", "post_message"),
)

TIME = AgentSpec(
    name="time",
    title="Time agent (planner)",
    goal="Assess the programme impact, and argue for protecting the completion date.",
    tools=("added_duration", "run_cpm", "evaluate_option", "ask_agent", "read_blackboard", "post_message"),
)

COMMERCIAL = AgentSpec(
    name="commercial",
    title="Commercial agent",
    goal="Weigh cost contingency against time buffer, and find the full option set.",
    tools=("search_options", "evaluate_option", "check_buffer", "ask_agent", "read_blackboard", "post_message"),
)

VERIFIER = AgentSpec(
    name="verifier",
    title="Verifier agent",
    goal="Explain the result of the deterministic checks on another agent's message.",
    tools=("post_message",),
    model_tier="light",
)

MODERATOR = AgentSpec(
    name="moderator",
    title="Moderator agent",
    goal="Run the debate, synthesise the options and prepare the decision for a person.",
    tools=("read_blackboard", "search_options", "propose_action", "post_message"),
)

ROSTER: dict[str, AgentSpec] = {a.name: a for a in (MODERATOR, INTAKE, CONTRACT, COST, TIME, COMMERCIAL, VERIFIER)}
DEBATERS: tuple[str, ...] = ("cost", "time", "commercial")


def get_agent(name: str) -> AgentSpec:
    try:
        return ROSTER[name]
    except KeyError:
        raise KeyError(f"Unknown agent: {name}. Defined: {', '.join(ROSTER)}") from None
