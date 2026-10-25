"""Orchestrator: runs the stages, routes questions between agents, runs the Verifier on every
message, tracks stances, enforces the approval gate and executes approved actions (SPEC 10).

The orchestrator fixes the stages (guardrails). Inside each stage, agents choose their own tools,
arguments, questions and positions.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Literal

from pvr.agents.base import AgentTurn, run_agent_turn
from pvr.agents.roster import DEBATERS, get_agent
from pvr.config import RUNS_DIR, Settings
from pvr.engines import options as options_engine
from pvr.engines.common import EngineError
from pvr.events.bus import EventBus, Sink
from pvr.events.store import JsonlSink
from pvr.ids import IdGen, new_run_id, now_iso
from pvr.llm.client import LLM
from pvr.models import AgentMessage, ProjectData, RunContext
from pvr.orchestrator.actions import ExecutedAction, execute_actions
from pvr.orchestrator.approvals import ApprovalError, Decision, make_approval, make_rejection
from pvr.orchestrator.context import RunSession
from pvr.orchestrator.stages import (
    answer_instruction, correction_instruction, debate_instruction, stage_instruction, verifier_instruction,
)
from pvr.orchestrator.verifier import VerificationResult, clause_refs, verify_message
from pvr.tools.registry import REGISTRY, ToolOutcome, ToolRegistry

# Tool results the orchestrator copies to the blackboard, so later stages can read them.
TOOL_SECTIONS: dict[str, str] = {
    "get_change_request": "change", "compare_drawing_revisions": "change", "check_notice": "change",
    "quantify_change": "quantities", "price_change": "cost", "added_duration": "schedule_impact",
    "run_cpm": "schedule_impact", "evaluate_option": "options", "search_options": "options",
    "check_buffer": "buffer", "compare_contractor_claim": "claim_comparison",
}
ANSWER_MAX_STEPS = 5


class RunAborted(RuntimeError):
    """The run cannot continue, for example because the language model cannot be reached."""


def _checked(turn: AgentTurn) -> AgentTurn:
    """Stop the run when an agent could not reach the model: an assessment without its agents must not
    go on to an approval."""
    if turn.model_unavailable:
        raise RunAborted(f"The {turn.agent} agent could not reach the language model: {turn.error}")
    return turn
State = Literal["created", "running", "awaiting_approval", "completed", "rejected", "failed"]


class Orchestrator:
    def __init__(self, session: RunSession, llm: LLM, registry: ToolRegistry = REGISTRY,
                 concurrent: bool = True) -> None:
        self.session = session
        self.llm = llm
        self.registry = registry
        self.concurrent = concurrent
        self.state: State = "created"
        self.stances: dict[str, dict[str, str | None]] = {}
        self.current_stance: dict[str, str | None] = {}
        self.presented: list[str] = []
        self.decision: Decision | None = None
        self.executed: list[ExecutedAction] = []
        self.debate_rounds = 0
        self.debate_stop_reason = ""
        session.ask_handler = self._ask
        session.tool_hooks.append(self._record_tool_result)

    # --- public API -------------------------------------------------------------------------------

    def run_until_approval(self) -> dict[str, Any]:
        """Stages 1 to 5, then request approval. Returns the approval request payload."""
        if self.state != "created":
            raise RuntimeError("This run has already started")
        self.state = "running"
        try:
            self._stage("intake", self._intake)
            self._stage("assessment", self._assessment)
            self._stage("commercial", self._commercial)
            self._stage("debate", self._debate)
            self._stage("synthesis", self._synthesis)
        except RunAborted as exc:
            self.state = "failed"
            self.session.bus.emit("run.error", {"error": str(exc), "fatal": True, "stage": self.session.stage})
            raise
        return self._request_approval()

    def approve(self, option_id: str, action_ids: list[str], approver_name: str, approver_role: str
                ) -> list[ExecutedAction]:
        """Record a person's approval, then execute the approved actions (stage 7)."""
        if self.state != "awaiting_approval":
            raise ApprovalError("This run is not waiting for approval")
        self.decision = make_approval(self.session, self.presented, option_id, action_ids, approver_name,
                                      approver_role)
        self.session.blackboard.write("decision", self.decision.model_dump(), self.decision.approver_name)
        self.session.bus.emit("approval.granted", self.decision.model_dump())
        self.session.stage = "action"
        self.session.bus.emit("stage.started", {"stage": "action"})
        self.executed = self.execute()
        self.session.bus.emit("stage.completed", {"stage": "action"})
        self.state = "completed"
        self.session.bus.emit("run.completed", {"status": "approved", "option_id": option_id,
                                                "executed_actions": [e.action_id for e in self.executed]})
        return self.executed

    def reject(self, approver_name: str, approver_role: str, reason: str) -> Decision:
        if self.state != "awaiting_approval":
            raise ApprovalError("This run is not waiting for approval")
        self.decision = make_rejection(approver_name, approver_role, reason)
        self.session.blackboard.write("decision", self.decision.model_dump(), self.decision.approver_name)
        self.session.bus.emit("approval.rejected", self.decision.model_dump())
        self.state = "rejected"
        self.session.bus.emit("run.completed", {"status": "rejected"})
        return self.decision

    def execute(self) -> list[ExecutedAction]:
        """Execute approved actions. Raises ApprovalError (and emits run.error) without an approval."""
        return execute_actions(self.session, self.decision, dict(self.current_stance), list(self.presented))

    # --- stages -------------------------------------------------------------------------------------

    def _stage(self, stage: str, body: Any) -> None:
        self.session.stage = stage
        self.session.round = 0
        self.session.bus.emit("stage.started", {"stage": stage})
        extra = body() or {}
        self.session.bus.emit("stage.completed", {"stage": stage, **extra})

    def _intake(self) -> None:
        # Reference run for the UI: the baseline programme, so the Gantt chart can show baseline against
        # impacted bars from events. It is not written to the blackboard and does not steer any agent.
        self.registry.dispatch(self.session, "run_cpm", {"include_change_durations": False}, agent="orchestrator")
        message = self._turn("intake", stage_instruction("intake"), sections=[], inbox=[])
        if message:
            self.session.blackboard.merge("change", "intake_summary", message.content, "intake")

    def _assessment(self) -> None:
        agents = ["contract", "cost", "time"]
        instruction = stage_instruction("assessment")
        if self.concurrent:
            with ThreadPoolExecutor(max_workers=len(agents)) as pool:
                results = list(pool.map(lambda a: self._turn(a, instruction, ["change"], []), agents))
        else:
            results = [self._turn(a, instruction, ["change"], []) for a in agents]
        for agent, message in zip(agents, results):
            if agent == "contract" and message:
                self.session.blackboard.write("contract_findings", {
                    "summary": message.content, "clauses": sorted(set(clause_refs(message.content))),
                    "claims": [c.model_dump() for c in message.claims]}, "contract")

    def _commercial(self) -> None:
        self._turn("commercial", stage_instruction("commercial"), ["change"], self._discussion())

    def _debate(self) -> dict[str, Any]:
        s = self.session
        max_rounds = max(1, s.settings.max_debate_rounds)
        pareto = options_engine.search_options(s.ctx, s.data).pareto_option_ids
        previous: dict[str, str | None] | None = None
        reason = "max_rounds"
        for round_ in range(1, max_rounds + 1):
            s.round = round_
            for agent in DEBATERS:
                stances = {a: self.current_stance.get(a) for a in DEBATERS}
                self._turn(agent, debate_instruction(round_, max_rounds, stances, agent), ["options"],
                           self._discussion())
            self.debate_rounds = round_
            now = {a: self.current_stance.get(a) for a in DEBATERS}
            if round_ == 1 and len(pareto) == 1:
                reason = "single_pareto_option"
                break
            if previous is not None and now == previous:
                reason = "stances_unchanged"
                break
            previous = now
        self.debate_stop_reason = reason
        return {"rounds": self.debate_rounds, "stop_reason": reason}

    def _synthesis(self) -> None:
        s = self.session
        message = self._turn("moderator", stage_instruction("synthesis"), ["stances", "pending_actions"],
                             self._discussion())
        valid = [o for o in (message.proposals if message else []) if o in s.evaluated_options]
        source = "moderator"
        if not valid or (message and message.verification.status == "fail"):
            # The Moderator's summary did not pass: fall back to the engine's Pareto set, and say so.
            valid = options_engine.search_options(s.ctx, s.data).pareto_option_ids[:3]
            source = "pareto_fallback"
        evaluated = {o: options_engine.evaluate_option(s.ctx, s.data, options_engine.parse_option_id(o, s.data))
                     for o in valid}
        self.presented = sorted(valid, key=lambda o: (evaluated[o].delay_working_days, evaluated[o].total_cost_aed))
        s.bus.emit("options.final", {
            "source": source,
            "options": [{**evaluated[o].model_dump(mode="json"),
                         "supported_by": [a for a in DEBATERS if self.current_stance.get(a) == o]}
                        for o in self.presented],
            "stances": {a: self.current_stance.get(a) for a in DEBATERS},
            "debate_rounds": self.debate_rounds, "debate_stop_reason": self.debate_stop_reason,
        })

    def _request_approval(self) -> dict[str, Any]:
        s = self.session
        s.stage = "approval"
        s.bus.emit("stage.started", {"stage": "approval"})
        payload = {
            "options": self.presented,
            "pending_actions": [a.model_dump() for a in s.pending_actions],
            "stances": {a: self.current_stance.get(a) for a in DEBATERS},
        }
        s.bus.emit("approval.requested", payload)
        self.state = "awaiting_approval"
        return payload

    # --- turns, verification and corrections --------------------------------------------------------

    def _discussion(self) -> list[AgentMessage]:
        """Final messages from the assessment onward (no superseded ones, no Verifier notes)."""
        with self.session.lock:
            return [m for m in self.session.messages
                    if m.stage in ("assessment", "commercial", "debate") and m.superseded_by is None
                    and m.intent not in ("VERIFY", "ASK")]

    def _turn(self, agent: str, instruction: str, sections: list[str], inbox: list[AgentMessage],
              depth: int = 0, max_steps: int | None = None) -> AgentMessage | None:
        """One agent turn, verified, with one correction turn on failure. Returns the final message."""
        spec = get_agent(agent)
        turn = _checked(run_agent_turn(self.session, spec, self.llm, instruction, blackboard_sections=sections,
                                       inbox=inbox, registry=self.registry, max_steps=max_steps, depth=depth))
        message = turn.message
        if message is None:
            return None
        result = self._verify(message)
        if not result.passed:
            note = self._explain_failure(message, result)
            retry = _checked(run_agent_turn(
                self.session, spec, self.llm, correction_instruction(message.message_id, result.issues),
                blackboard_sections=sections, inbox=[message] + ([note] if note else []),
                registry=self.registry, max_steps=max_steps, depth=depth))
            if retry.message is not None:
                corrected = retry.message
                corrected.corrects = message.message_id
                message.superseded_by = corrected.message_id
                self.session.bus.emit("message.corrected", {
                    "original_message_id": message.message_id, "corrected_message_id": corrected.message_id,
                    "agent": agent})
                second = self._verify(corrected, unresolved_on_fail=True)
                message = corrected
                result = second
        if depth == 0 and self.session.stage in ("assessment", "commercial", "debate"):
            self._record_stance(agent, message)
        return message

    def _verify(self, message: AgentMessage, unresolved_on_fail: bool = False) -> VerificationResult:
        result = verify_message(self.session, message)
        message.verification.status = "pass" if result.passed else "fail"
        message.verification.issues = result.issues
        self.session.bus.emit("verification.result", {
            "message_id": message.message_id, "agent": message.from_agent, "status": message.verification.status,
            "issues": result.issues, "unresolved": unresolved_on_fail and not result.passed,
            "claims_checked": len(message.claims)})
        return result

    def _explain_failure(self, message: AgentMessage, result: VerificationResult) -> AgentMessage | None:
        """The Verifier agent tells the author what is wrong (the checks themselves are deterministic)."""
        turn = _checked(run_agent_turn(self.session, get_agent("verifier"), self.llm,
                                       verifier_instruction(message.from_agent, message.message_id, result.issues),
                                       inbox=[message], registry=self.registry, max_steps=2, depth=1))
        return turn.message

    def _record_stance(self, agent: str, message: AgentMessage) -> None:
        s = self.session
        label = f"round_{s.round}" if s.stage == "debate" else s.stage
        stance = message.stance if message.stance in s.evaluated_options else None
        with s.lock:
            self.stances.setdefault(label, {})[agent] = stance
            previous = self.current_stance.get(agent)
            self.current_stance[agent] = stance if stance is not None else previous
            snapshot = {k: dict(v) for k, v in self.stances.items()}
        s.blackboard.write("stances", snapshot, "orchestrator")
        if stance is not None and stance != previous:
            s.bus.emit("stance.changed", {"agent": agent, "from": previous, "to": stance, "when": label,
                                          "message_id": message.message_id})

    # --- ask_agent and blackboard ----------------------------------------------------------------------

    def _ask(self, asker: str, target: str, question: str) -> dict[str, Any]:
        s = self.session
        ask = AgentMessage(message_id=s.ids.next("M"), run_id=s.run_id, stage=s.stage, round=s.round,
                           from_agent=asker, to=target, intent="ASK", content=question, timestamp=now_iso())
        s.add_message(ask)
        s.bus.emit("message.posted", ask.model_dump(mode="json"))
        s.bus.emit("ask.sent", {"message_id": ask.message_id, "from": asker, "to": target, "question": question})
        answer = self._turn(target, answer_instruction(asker, question), ["change"], [ask], depth=1,
                            max_steps=ANSWER_MAX_STEPS)
        if answer is None:
            s.bus.emit("ask.answered", {"message_id": ask.message_id, "from": target, "to": asker,
                                        "answer_message_id": None})
            raise EngineError(f"The {target} agent did not answer")
        s.bus.emit("ask.answered", {"message_id": ask.message_id, "from": target, "to": asker,
                                    "answer_message_id": answer.message_id})
        return {"answer_from": target, "message_id": answer.message_id, "content": answer.content,
                "claims": [c.model_dump() for c in answer.claims], "verification": answer.verification.status}

    def _record_tool_result(self, outcome: ToolOutcome) -> None:
        section = TOOL_SECTIONS.get(outcome.tool)
        if section is None or outcome.agent == "orchestrator":
            return
        key = outcome.result.get("option_id", outcome.tool) if outcome.tool in ("evaluate_option", "check_buffer") \
            else outcome.tool
        self.session.blackboard.merge(section, key, outcome.result, outcome.agent)


# --- run factory ------------------------------------------------------------------------------------------


def start_run(
    ctx: RunContext,
    data: ProjectData,
    settings: Settings,
    llm: LLM,
    runs_dir: Path = RUNS_DIR,
    sinks: list[Sink] | None = None,
    concurrent: bool = True,
    run_id: str | None = None,
) -> tuple[Orchestrator, JsonlSink]:
    """Create a run with its folder and trace (`runs/<id>/events.jsonl`). Close the sink when done."""
    rid = run_id or new_run_id()
    ids = IdGen()
    run_dir = runs_dir / rid
    sink = JsonlSink(run_dir / "events.jsonl")
    bus = EventBus(rid, ids, [sink] + list(sinks or []))
    session = RunSession(run_id=rid, ctx=ctx, data=data, settings=settings, ids=ids, bus=bus, run_dir=run_dir)
    bus.emit("run.started", {"context": ctx.model_dump(mode="json"), "kind": "full",
                             "model": settings.openai_model, "model_light": settings.light_model})
    return Orchestrator(session, llm, concurrent=concurrent), sink
