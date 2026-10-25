"""Decision replay: a recorded run brought back to its approval gate, so a person decides again.

A recorded run already holds its decision. For a demonstration the decision should be taken in the room,
so this module copies the recording up to `approval.requested` into a new run, rebuilds the state the
approval step needs (context, messages and their verification, pending actions, presented options,
stances) and returns an orchestrator waiting for approval. Approving it executes the actions as in a
live run: the step after approval is code only, so a decision replay needs no language model.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pvr.config import RUNS_DIR, Settings
from pvr.events.bus import EventBus
from pvr.events.store import JsonlSink
from pvr.ids import IdGen, new_run_id
from pvr.llm.client import LLMError, LLMResponse
from pvr.models import AgentMessage, Event, ProjectData, RunContext
from pvr.orchestrator.context import PendingAction, RunSession
from pvr.orchestrator.orchestrator import Orchestrator


# The messages whose stance the orchestrator records: an agent's own turn in these stages.
STANCE_STAGES = ("assessment", "commercial", "debate")
STANCE_INTENTS = ("ASSESS", "PROPOSE", "CHALLENGE", "AGREE")


class DecisionReplayError(ValueError):
    """The recording cannot be brought back to a decision (for example it never reached one)."""


class NoModel:
    """The language model of a decision replay: the approval step never calls it."""

    def complete(self, **_: Any) -> LLMResponse:
        raise LLMError("A decision replay does not call the language model")


def events_until_decision(events: list[Event]) -> list[Event]:
    """The recorded events up to and including the approval request."""
    started = events[0] if events else None
    if started is None or started.type != "run.started" or started.payload.get("kind") != "full":
        raise DecisionReplayError("Only a full multi-agent run can be replayed to its decision")
    for i, event in enumerate(events):
        if event.type == "approval.requested":
            return events[: i + 1]
    raise DecisionReplayError("This run never reached the decision, so it can only be replayed as recorded")


def _copy(event: Event, run_id: str, old_run_id: str, replay_of: str) -> Event:
    """The event under the new run id. The first event also says which recording it came from."""
    payload = dict(event.payload)
    if payload.get("run_id") == old_run_id:
        payload["run_id"] = run_id
    if event.type == "run.started":
        payload["replay_of"] = replay_of
    return event.model_copy(update={"run_id": run_id, "payload": payload})


def restore_for_decision(
    events: list[Event],
    replay_of: str,
    data: ProjectData,
    settings: Settings,
    runs_dir: Path = RUNS_DIR,
    run_id: str | None = None,
) -> tuple[Orchestrator, JsonlSink]:
    """A new run holding the recording up to its approval request, waiting for a person's decision.
    Raises DecisionReplayError when the recording has no approval request. Close the sink when done."""
    recorded = events_until_decision(events)
    old_run_id = recorded[0].run_id
    rid = run_id or new_run_id()
    copied = [_copy(e, rid, old_run_id, replay_of) for e in recorded]

    ids = IdGen()
    ids.resume("E", len(copied))
    run_dir = runs_dir / rid
    sink = JsonlSink(run_dir / "events.jsonl")
    bus = EventBus(rid, ids, [sink])
    bus.restore(copied)

    ctx = RunContext.model_validate(copied[0].payload["context"])
    session = RunSession(run_id=rid, ctx=ctx, data=data, settings=settings, ids=ids, bus=bus, run_dir=run_dir)
    session.stage = "approval"

    messages: dict[str, AgentMessage] = {}
    stances: dict[str, str | None] = {}
    for event in copied:
        p = event.payload
        if event.type == "message.posted":
            message = AgentMessage.model_validate(p)
            messages[message.message_id] = message
            session.add_message(message)
            if message.stage in STANCE_STAGES and message.intent in STANCE_INTENTS:
                stances.setdefault(message.from_agent, None)  # the agent took part, with or without a stance
        elif event.type == "verification.result" and p.get("message_id") in messages:
            messages[p["message_id"]].verification.status = p["status"]
            messages[p["message_id"]].verification.issues = list(p.get("issues", []))
        elif event.type == "message.corrected" and p.get("original_message_id") in messages:
            messages[p["original_message_id"]].superseded_by = p["corrected_message_id"]
        elif event.type == "action.proposed":
            session.pending_actions.append(PendingAction.model_validate(p))
        elif event.type == "stance.changed":
            stances[p["agent"]] = p["to"]

    request = copied[-1].payload
    orchestrator = Orchestrator(session, NoModel())
    orchestrator.presented = list(request.get("options", []))
    orchestrator.current_stance = stances
    orchestrator.state = "awaiting_approval"
    return orchestrator, sink
