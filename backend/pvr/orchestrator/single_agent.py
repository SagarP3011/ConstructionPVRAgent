"""Run one agent on its own (Phase 2), with earlier blackboard sections pre-filled from engines."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pvr.agents.base import AgentTurn, run_agent_turn
from pvr.agents.roster import get_agent
from pvr.config import RUNS_DIR, Settings
from pvr.engines import change
from pvr.events.bus import EventBus, Sink
from pvr.events.store import JsonlSink
from pvr.ids import IdGen, new_run_id
from pvr.llm.client import LLM
from pvr.models import ProjectData, RunContext
from pvr.orchestrator.context import RunSession
from pvr.orchestrator.stages import stage_instruction
from pvr.tools.registry import to_jsonable

PREFILLED_BY = "engines (pre-filled for a single-agent run)"


def new_session(
    ctx: RunContext,
    data: ProjectData,
    settings: Settings,
    runs_dir: Path | None = RUNS_DIR,
    run_id: str | None = None,
    sinks: list[Sink] | None = None,
) -> tuple[RunSession, JsonlSink | None]:
    """A RunSession with an event bus; writes `runs/<run_id>/events.jsonl` unless runs_dir is None."""
    rid = run_id or new_run_id()
    ids = IdGen()
    sink = JsonlSink(runs_dir / rid / "events.jsonl") if runs_dir is not None else None
    bus = EventBus(rid, ids, ([sink] if sink else []) + list(sinks or []))
    session = RunSession(run_id=rid, ctx=ctx, data=data, settings=settings, ids=ids, bus=bus)
    bus.emit("run.started", {"context": ctx.model_dump(mode="json"), "kind": "single_agent"})
    return session, sink


def intake_section(session: RunSession) -> dict[str, Any]:
    """What the Intake stage would package: the change request, the element comparison and, in
    contractor PVR mode, the notice check."""
    ctx, data = session.ctx, session.data
    request = change.get_change_request(ctx, data)
    content: dict[str, Any] = {
        "change_request": to_jsonable(request),
        "drawing_comparison": to_jsonable(change.compare_drawing_revisions(ctx, data)),
    }
    if request.variation_instruction and request.contractor_pvr:
        from pvr.engines.contract import check_notice

        content["notice_check"] = to_jsonable(
            check_notice(request.variation_instruction.date, request.contractor_pvr.date))
    return content


def run_single_agent(
    agent_name: str,
    ctx: RunContext,
    data: ProjectData,
    settings: Settings,
    llm: LLM,
    runs_dir: Path | None = RUNS_DIR,
    sinks: list[Sink] | None = None,
) -> tuple[RunSession, AgentTurn]:
    """Pre-fill the `change` section, run the agent's assessment turn and close the trace."""
    session, sink = new_session(ctx, data, settings, runs_dir, sinks=sinks)
    try:
        session.blackboard.write("change", intake_section(session), PREFILLED_BY)
        session.stage = "assessment"
        session.bus.emit("stage.started", {"stage": "assessment"})
        turn = run_agent_turn(session, get_agent(agent_name), llm, stage_instruction("assessment"),
                              blackboard_sections=["change"])
        session.bus.emit("stage.completed", {"stage": "assessment"})
        session.bus.emit("run.completed", {"status": turn.status, "agent": agent_name})
        return session, turn
    finally:
        if sink:
            sink.close()
