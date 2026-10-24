"""A scripted room of fake agents for orchestrator tests.

Each fake agent calls one tool on its first step, then posts a message that cites real facts from
the run. It reads the stage from the instruction, so it behaves sensibly in every stage. Tests
override single agents with explicit scripts where they need a specific behaviour.
"""

from __future__ import annotations

import re
from typing import Any

from pvr.engines import options as options_engine
from pvr.llm.client import LLMResponse
from pvr.llm.fake import RoutedFakeLLM, tool_call, tool_calls
from pvr.orchestrator.context import RunSession

FIRST_TOOL: dict[str, list[tuple[str, dict[str, Any]]]] = {
    "intake": [("get_change_request", {})],
    "contract": [("search_contract", {"query": "valuation of variations"})],
    "cost": [("price_change", {})],
    "time": [("added_duration", {})],
    "commercial": [("search_options", {})],
    "moderator": [("search_options", {}), ("propose_action", {"type": "draft_pvr_form", "reason": "Record"}),
                  ("propose_action", {"type": "notify", "reason": "Inform",
                                      "payload": {"recipients": ["planner", "quantity surveyor", "contracts"],
                                                  "message": "Decision needed."}})],
}
PREFERENCE = {"cost": -1, "time": 0, "commercial": 0}  # index into the Pareto list


def _context(messages: list[dict[str, Any]]) -> str:
    return str(messages[1]["content"])


def _started(messages: list[dict[str, Any]]) -> bool:
    return any(m["role"] == "assistant" for m in messages)


def post(to: str, intent: str, content: str, claims: list[dict[str, Any]] | None = None,
         stance: str | None = None, proposals: list[str] | None = None) -> LLMResponse:
    return tool_call("post_message", {"to": to, "intent": intent, "content": content, "claims": claims or [],
                                      "stance": stance, "proposals": proposals or []})


class Room:
    """Holds the session (set after start_run) so fake agents can cite real fact ids."""

    def __init__(self) -> None:
        self.session: RunSession | None = None

    def pareto(self) -> list[str]:
        assert self.session is not None
        return options_engine.search_options(self.session.ctx, self.session.data).pareto_option_ids

    def cost_claim(self) -> tuple[str, list[dict[str, Any]]]:
        assert self.session is not None
        facts = self.session.facts.find("price_change", "direct_cost_aed")
        if not facts:
            return "Cost assessed at BOQ rates (clause 13.3).", []
        f = facts[-1]
        return (f"Direct cost AED {f.value} at BOQ rates (clause 13.3).",
                [{"label": "direct cost", "value": f.value, "unit": "AED", "fact_id": f.fact_id}])

    def behave(self, agent: str, messages: list[dict[str, Any]]) -> LLMResponse:
        text = _context(messages)
        if agent == "verifier":
            author = re.search(r"from the (\w+) agent", text)
            return post(author.group(1) if author else "all", "VERIFY", "Please cite a fact for every number.")
        asked = re.search(r"The (\w+) agent asks you", text)
        if asked:
            return post(asked.group(1), "ANSWER", "Under clause 8.4 only delay to completion counts.")
        if not _started(messages) and agent in FIRST_TOOL and "failed verification" not in text:
            return tool_calls(FIRST_TOOL[agent])
        if "Stage: debate" in text:
            pareto = self.pareto()
            stance = pareto[PREFERENCE[agent]]
            target = {"cost": "time", "time": "cost", "commercial": "cost"}[agent]
            intent = "CHALLENGE" if agent == "time" else "PROPOSE"
            return post(target, intent, f"I prefer {stance}.", stance=stance)
        if "Stage: synthesis" in text:
            return post("all", "SUMMARISE", "Options for the person to decide.", proposals=self.pareto())
        content, claims = self.cost_claim() if agent == "cost" else (f"{agent} assessment done.", [])
        stance = self.pareto()[0] if agent == "commercial" else None
        return post("all", "ASSESS", content, claims, stance=stance)

    def llm(self, scripts: dict[str, list[Any]] | None = None) -> RoutedFakeLLM:
        return RoutedFakeLLM(scripts or {}, fallback=self.behave)
