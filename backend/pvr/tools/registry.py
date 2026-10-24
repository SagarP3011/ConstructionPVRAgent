"""Tool registry: engine and orchestration tools with JSON schemas, context injection and dispatch.

Agents pass only the arguments that are theirs to choose (queries, clause ids, option crews).
The run context and data are injected from the RunSession. Every number in a result is
registered as a fact, and the model sees the result with fact ids next to the values.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from pvr.engines import boq, buffer, change, contract, cost, cpm, options, productivity, quantities
from pvr.engines.common import EngineError
from pvr.ids import now_iso
from pvr.models import AgentMessage, Claim, Intent
from pvr.orchestrator.blackboard import SECTIONS
from pvr.orchestrator.context import PendingAction, RunSession, current_turn
from pvr.tools.citations import extract_citations, merge_claims
from pvr.tools.facts import Fact


class ToolArgs(BaseModel):
    """Base for tool arguments: unknown arguments are rejected."""

    model_config = ConfigDict(extra="forbid")


class NoArgs(ToolArgs):
    pass


Handler = Callable[[RunSession, Any, str], Any]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args_model: type[ToolArgs]
    handler: Handler
    kind: Literal["engine", "orchestration"] = "engine"
    available: Callable[[RunSession], bool] = field(default=lambda session: True)

    def openai_schema(self) -> dict[str, Any]:
        """Function definition for OpenAI Chat Completions tool calling."""
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description,
                         "parameters": clean_schema(self.args_model.model_json_schema())},
        }


class ToolOutcome(BaseModel):
    tool_call_id: str
    tool: str
    agent: str
    args: dict[str, Any]
    ok: bool
    result: Any = None
    error: str = ""
    facts: list[Fact] = Field(default_factory=list)
    model_content: str


def clean_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Inline `$defs` references and drop `title` keys, for a compact model-facing schema."""
    defs = schema.get("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(copy.deepcopy(defs[node["$ref"].split("/")[-1]]))
            return {k: walk(v) for k, v in node.items() if k not in ("title", "$defs")}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    out = walk(schema)
    out.setdefault("properties", {})
    out["additionalProperties"] = False
    return out


def to_jsonable(value: Any) -> Any:
    """Engine results (Pydantic models, lists of them, dates) as plain JSON values."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: to_jsonable(v) for k, v in value.items()}
    if isinstance(value, date):
        return value.isoformat()
    return value


class ToolRegistry:
    """Named tools. `dispatch` runs one tool call for an agent and records it."""

    def __init__(self, tools: list[ToolSpec]) -> None:
        self._tools = {t.name: t for t in tools}

    def __contains__(self, name: object) -> bool:
        return name in self._tools

    def names(self) -> list[str]:
        return list(self._tools)

    def get(self, name: str) -> ToolSpec:
        return self._tools[name]

    def available_for(self, session: RunSession, allowed: list[str]) -> list[ToolSpec]:
        """The allowed tools that exist and are available in this run (for example, the claim check only
        in contractor PVR mode), in the order given."""
        return [self._tools[n] for n in allowed if n in self._tools and self._tools[n].available(session)]

    def dispatch(
        self,
        session: RunSession,
        name: str,
        raw_args: str | dict[str, Any] | None,
        agent: str,
        allowed: list[str] | None = None,
    ) -> ToolOutcome:
        """Validate and run one tool call, register facts in the result and emit tool events."""
        call_id = session.ids.next("T")
        args, parse_error = _parse_args(raw_args)
        session.bus.emit("tool.called", {"tool_call_id": call_id, "agent": agent, "tool": name, "args": args})

        spec = self._tools.get(name)
        error = parse_error
        if not error and spec is None:
            error = f"Unknown tool: {name}"
        elif not error and allowed is not None and name not in allowed:
            error = f"Tool {name} is not available to {agent}"
        elif not error and not spec.available(session):  # type: ignore[union-attr]
            error = f"Tool {name} is not available in this run"

        result: Any = None
        if not error:
            assert spec is not None
            try:
                parsed = spec.args_model.model_validate(args)
                result = to_jsonable(spec.handler(session, parsed, agent))
            except ValidationError as exc:
                error = "Invalid arguments: " + "; ".join(
                    f"{'.'.join(str(p) for p in e['loc']) or 'arguments'}: {e['msg']}" for e in exc.errors()
                )
            except EngineError as exc:
                error = str(exc)

        if error:
            outcome = ToolOutcome(
                tool_call_id=call_id, tool=name, agent=agent, args=args, ok=False, error=error,
                model_content=json.dumps({"tool_call_id": call_id, "error": error}),
            )
        else:
            annotated, facts = session.facts.register_result(call_id, name, result)
            for fact in facts:
                session.bus.emit("fact.registered", fact.model_dump())
            outcome = ToolOutcome(
                tool_call_id=call_id, tool=name, agent=agent, args=args, ok=True, result=result, facts=facts,
                model_content=json.dumps({"tool_call_id": call_id, "result": annotated}, separators=(",", ":")),
            )
        session.bus.emit("tool.result", {
            "tool_call_id": call_id, "agent": agent, "tool": name, "ok": outcome.ok, "result": outcome.result,
            "error": outcome.error, "fact_ids": [f.fact_id for f in outcome.facts],
        })
        if outcome.ok:
            _track_options(session, outcome)
            for hook in list(session.tool_hooks):
                hook(outcome)
        return outcome


def _track_options(session: RunSession, outcome: ToolOutcome) -> None:
    """Remember every option evaluated in this run (the Verifier checks option ids against these)."""
    if outcome.tool == "search_options":
        found = outcome.result["options"]
    elif outcome.tool in ("evaluate_option", "check_buffer"):  # check_buffer evaluates the option too
        found = [outcome.result]
    else:
        return
    for option in found:
        with session.lock:
            new = option["option_id"] not in session.evaluated_options
            session.evaluated_options[option["option_id"]] = option
        if new:
            session.bus.emit("option.evaluated", {
                "option_id": option["option_id"], "agent": outcome.agent, "tool_call_id": outcome.tool_call_id,
                "delay_working_days": option["delay_working_days"], "total_cost_aed": option["total_cost_aed"],
            })


def _parse_args(raw: str | dict[str, Any] | None) -> tuple[dict[str, Any], str]:
    if raw is None or raw == "":
        return {}, ""
    if isinstance(raw, dict):
        return raw, ""
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {}, f"Arguments are not valid JSON: {exc.msg}"
    if not isinstance(value, dict):
        return {}, "Arguments must be a JSON object"
    return value, ""


# --- argument models -------------------------------------------------------------------------


class QueryArgs(ToolArgs):
    query: str = Field(min_length=1, description="Words to search for")
    top_k: int = Field(default=5, ge=1, le=10, description="Number of results")


class ContractQueryArgs(ToolArgs):
    query: str = Field(min_length=1, description="Words to search for")
    top_k: int = Field(default=3, ge=1, le=11, description="Number of results")


class ClauseArgs(ToolArgs):
    clause_id: str = Field(description="Clause number, for example 13.3")


class BoqCodeArgs(ToolArgs):
    code: str = Field(description="BOQ code, for example R-02-010")


class NoticeArgs(ToolArgs):
    event_date: date = Field(description="Date of the event (YYYY-MM-DD)")
    notice_date: date = Field(description="Date the notice was given (YYYY-MM-DD)")
    limit_days: int = Field(default=28, ge=0, description="Notice period in calendar days")


class CpmArgs(ToolArgs):
    include_change_durations: bool = Field(
        default=True, description="Start from the programme with this change's added durations (false: baseline)")
    duration_overrides: dict[str, int] = Field(
        default_factory=dict, description="Activity id -> duration in working days, applied last")


class OptionArgs(ToolArgs):
    extra_crews_on: list[str] = Field(description="Activity ids that get one extra crew each; empty for none")


class OptionIdArgs(ToolArgs):
    option_id: str = Field(description="Option id, for example OPT-NONE or OPT-A120")


class BlackboardArgs(ToolArgs):
    section: Literal[SECTIONS] = Field(description="Blackboard section to read")  # type: ignore[valid-type]


class AskArgs(ToolArgs):
    to: str = Field(description="The agent to ask")
    question: str = Field(min_length=1, description="One specific question")


ActionType = Literal["create_task", "draft_pvr_form", "draft_verification_report", "notify"]


class ProposeActionArgs(ToolArgs):
    type: ActionType = Field(description="Kind of action")
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="create_task: {title, description, owner}; notify: {recipients: [roles], message}; "
                    "draft_pvr_form and draft_verification_report: {}")
    reason: str = Field(min_length=1, description="Why this action is needed")


class PostMessageArgs(ToolArgs):
    to: str = Field(description="Agent name, or 'all'")
    intent: Intent
    content: str = Field(min_length=1, description="Your message in clear, plain English")
    claims: list[Claim] = Field(
        default_factory=list,
        description="Every number or date in content, each with the fact_id from a tool result that supports it")
    stance: str | None = Field(default=None, description="Your preferred option id (OPT-...), or null")
    proposals: list[str] = Field(default_factory=list,
                                 description="Option ids (OPT-...) you propose; never action ids")

    @field_validator("claims", "proposals", mode="before")
    @classmethod
    def _none_is_empty(cls, value: Any) -> Any:
        return [] if value is None else value

    @field_validator("claims")
    @classmethod
    def _claims_are_numbers_or_dates(cls, claims: list[Claim]) -> list[Claim]:
        for claim in claims:
            if isinstance(claim.value, str):
                text = claim.value.strip()
                try:
                    claim.value = float(text.replace(",", ""))
                except ValueError:
                    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
                        raise ValueError(
                            f"claim '{claim.label}' has value '{claim.value}': claims are for numbers and dates "
                            "(YYYY-MM-DD) only; mention ids and names in content without a claim") from None
        return claims

    @field_validator("stance", mode="before")
    @classmethod
    def _blank_stance(cls, value: Any) -> Any:
        return None if value in ("", "null", "none", "None") else value

    @field_validator("stance")
    @classmethod
    def _stance_is_option(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith("OPT-"):
            raise ValueError("stance must be an option id such as OPT-NONE, or null")
        return value

    @field_validator("proposals")
    @classmethod
    def _proposals_are_options(cls, value: list[str]) -> list[str]:
        wrong = [v for v in value if not v.startswith("OPT-")]
        if wrong:
            raise ValueError(f"proposals must be option ids (OPT-...), not {', '.join(wrong)}; "
                             "use propose_action for actions")
        return value


# --- handlers ----------------------------------------------------------------------------------


def _run_cpm(session: RunSession, args: CpmArgs, agent: str) -> cpm.CpmResult:
    durations = productivity.added_duration(session.ctx, session.data).new_durations() \
        if args.include_change_durations else {}
    durations.update(args.duration_overrides)
    return cpm.run_cpm(session.data, durations)


def _read_blackboard(session: RunSession, args: BlackboardArgs, agent: str) -> dict[str, Any]:
    entry = session.blackboard.read(args.section)
    if entry is None:
        return {"section": args.section, "empty": True, "filled_sections": session.blackboard.filled()}
    return entry.model_dump()


def known_agents() -> list[str]:
    from pvr.agents.roster import AGENT_NAMES

    return AGENT_NAMES


def _post_message(session: RunSession, args: PostMessageArgs, agent: str) -> dict[str, Any]:
    valid_to = known_agents() + ["all"]
    if args.to not in valid_to:
        raise EngineError(f"'to' must be one of: {', '.join(valid_to)}")
    reserved = {"VERIFY": "verifier", "SUMMARISE": "moderator"}
    if args.intent in reserved and agent != reserved[args.intent]:
        raise EngineError(f"Only the {reserved[args.intent]} agent posts {args.intent} messages")
    content, inline = extract_citations(args.content, session.facts)
    message = AgentMessage(
        message_id=session.ids.next("M"), run_id=session.run_id, stage=session.stage, round=session.round,
        from_agent=agent, to=args.to, intent=args.intent, content=content,
        claims=merge_claims(args.claims, inline), stance=args.stance, proposals=args.proposals,
        timestamp=now_iso(),
    )
    session.add_message(message)
    session.bus.emit("message.posted", message.model_dump(mode="json"))
    return {"message_id": message.message_id, "status": "posted"}


MAX_ASKS_PER_TURN = 2
ASKABLE = ("intake", "contract", "cost", "time", "commercial")


def _ask_agent(session: RunSession, args: AskArgs, agent: str) -> dict[str, Any]:
    turn = current_turn.get()
    if turn is not None and turn.depth >= 1:
        raise EngineError("You are answering a question; you cannot ask another agent in this turn")
    if args.to == agent or args.to not in ASKABLE:
        raise EngineError(f"'to' must be another of: {', '.join(a for a in ASKABLE if a != agent)}")
    if turn is not None and turn.asks >= MAX_ASKS_PER_TURN:
        raise EngineError(f"No more than {MAX_ASKS_PER_TURN} questions per turn")
    if session.ask_handler is None:
        raise EngineError("Other agents are not available in this run")
    if turn is not None:
        turn.asks += 1
    return session.ask_handler(agent, args.to, args.question)


def _propose_action(session: RunSession, args: ProposeActionArgs, agent: str) -> dict[str, Any]:
    payload = args.payload
    if args.type == "draft_verification_report" and not change.contractor_claim_applies(session.ctx):
        raise EngineError("A verification report applies only in contractor PVR mode")
    if args.type == "create_task" and not (payload.get("title") and payload.get("owner")):
        raise EngineError("create_task needs payload.title and payload.owner")
    if args.type == "notify" and not (isinstance(payload.get("recipients"), list) and payload["recipients"]
                                      and payload.get("message")):
        raise EngineError("notify needs payload.recipients (a list) and payload.message")
    with session.lock:
        # A run has one PVR form and one verification report; tasks and notifications may be several.
        duplicate = next((a for a in session.pending_actions if a.type == args.type
                          and a.type in ("draft_pvr_form", "draft_verification_report")), None)
        if duplicate:
            return {"action_id": duplicate.action_id, "status": "already proposed"}
        action = PendingAction(action_id=session.ids.next("ACT", width=3), type=args.type, payload=payload,
                               reason=args.reason, proposed_by=agent)
        session.pending_actions.append(action)
        snapshot = [a.model_dump() for a in session.pending_actions]
    session.blackboard.write("pending_actions", snapshot, "orchestrator")
    session.bus.emit("action.proposed", action.model_dump())
    return {"action_id": action.action_id, "status": "pending approval by a person"}


def _without_scores(hits: list[BaseModel]) -> list[dict[str, Any]]:
    """Search hits for the model: ranked best first, without the relevance score (it is not a figure
    about the project, and agents mistook it for one)."""
    return [h.model_dump(mode="json", exclude={"score"}) for h in hits]


def _contractor_mode(session: RunSession) -> bool:
    return change.contractor_claim_applies(session.ctx)


def build_registry() -> ToolRegistry:
    """All tools available to agents."""
    d = lambda s: s.data  # noqa: E731
    c = lambda s: s.ctx  # noqa: E731
    return ToolRegistry([
        ToolSpec("get_change_request",
                 "The change request for this run: change type, parameters, mode and instruction text. In "
                 "contractor PVR mode it also has the variation instruction and the contractor's PVR.",
                 NoArgs, lambda s, a, g: change.get_change_request(c(s), d(s))),
        ToolSpec("compare_drawing_revisions",
                 "Key parameter changes for the changed element: drawing revision differences where a revised "
                 "drawing exists, otherwise the element geometry and the parameter change.",
                 NoArgs, lambda s, a, g: change.compare_drawing_revisions(c(s), d(s))),
        ToolSpec("check_notice",
                 "Calendar days between an event and the notice given, and whether that is within the limit. "
                 "Use dates from the documents of this run.",
                 NoticeArgs, lambda s, a, g: contract.check_notice(a.event_date, a.notice_date, a.limit_days),
                 available=_contractor_mode),
        ToolSpec("search_contract", "Search the contract clauses (title and text). Returns the best clauses.",
                 ContractQueryArgs, lambda s, a, g: {"hits": _without_scores(contract.search_contract(a.query, d(s), a.top_k))}),
        ToolSpec("get_clause", "Full text of one contract clause.",
                 ClauseArgs, lambda s, a, g: contract.get_clause(a.clause_id, d(s))),
        ToolSpec("quantify_change",
                 "Measure this change: old, new and changed quantity for each related BOQ (bill of quantities) "
                 "line, plus related lines that are not affected and lines that need review, with reasons.",
                 NoArgs, lambda s, a, g: quantities.quantify_change(c(s), d(s))),
        ToolSpec("search_boq", "Search the BOQ by words or code. Returns code, description, unit, quantity, rate.",
                 QueryArgs, lambda s, a, g: {"hits": _without_scores(boq.search_boq(a.query, d(s), a.top_k))}),
        ToolSpec("get_boq_item", "One BOQ line by its exact code.",
                 BoqCodeArgs, lambda s, a, g: boq.get_boq_item(a.code, d(s))),
        ToolSpec("price_change",
                 "Price this change's quantity changes at BOQ contract rates. Returns cost lines, the direct "
                 "cost, and items left unpriced (under review or needing a new rate).",
                 NoArgs, lambda s, a, g: cost.price_change(c(s), d(s))),
        ToolSpec("compare_contractor_claim",
                 "Compare the contractor's claim line by line with the assessment: rates, quantities, "
                 "preliminaries, extension of time and notice, each with its clause.",
                 NoArgs, lambda s, a, g: cost.compare_contractor_claim(c(s), d(s)), available=_contractor_mode),
        ToolSpec("check_buffer",
                 "For one option: time buffer and cost contingency remaining, whether each holds, and any "
                 "budget uplift needed.",
                 OptionIdArgs, lambda s, a, g: buffer.check_buffer(c(s), d(s), a.option_id)),
        ToolSpec("added_duration",
                 "Added working days per programme activity caused by this change, from productivity rates.",
                 NoArgs, lambda s, a, g: productivity.added_duration(c(s), d(s))),
        ToolSpec("run_cpm",
                 "Critical path analysis of the programme: completion day and date, critical path, and "
                 "start, finish and float per activity.",
                 CpmArgs, _run_cpm),
        ToolSpec("evaluate_option",
                 "Cost and time of one option: this change with one extra crew on each listed activity "
                 "(empty list for no extra crews). Returns delay, cost parts, total, buffer and contingency left.",
                 OptionArgs, lambda s, a, g: options.evaluate_option(c(s), d(s), a.extra_crews_on)),
        ToolSpec("search_options",
                 "Evaluate every combination of extra crews for this change and return all options plus "
                 "the Pareto set (options no other option beats on both cost and delay).",
                 NoArgs, lambda s, a, g: options.search_options(c(s), d(s))),
        ToolSpec("read_blackboard", "Read a section of the shared blackboard written by earlier stages.",
                 BlackboardArgs, _read_blackboard, kind="orchestration"),
        ToolSpec("ask_agent",
                 "Ask another agent one specific question. The answer comes back as this tool's result, with "
                 "fact ids you can cite. At most two questions per turn.",
                 AskArgs, _ask_agent, kind="orchestration"),
        ToolSpec("propose_action",
                 "Propose an action for the person to approve: create_task, draft_pvr_form, "
                 "draft_verification_report or notify. Nothing is executed until a person approves it.",
                 ProposeActionArgs, _propose_action, kind="orchestration"),
        ToolSpec("post_message",
                 "Post your message to another agent or to all. This is the only way to end your turn.",
                 PostMessageArgs, _post_message, kind="orchestration"),
    ])


REGISTRY = build_registry()
