"""Run state snapshot, folded from a run's events only.

The same function serves live runs, stored runs and fixtures, so a snapshot never disagrees with the
event stream the UI renders.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from pvr.models import Event

RunState = Literal["running", "awaiting_approval", "completed", "rejected", "failed"]


class RunSnapshot(BaseModel):
    run_id: str
    kind: str = "full"
    state: RunState = "running"
    live: bool = False  # True while the server holds the run in memory (only then can it be approved)
    context: dict[str, Any] = Field(default_factory=dict)
    model: str | None = None
    model_light: str | None = None
    stage: str | None = None
    stages_completed: list[str] = Field(default_factory=list)
    debate: dict[str, Any] = Field(default_factory=dict)  # rounds and stop reason
    stances: dict[str, str | None] = Field(default_factory=dict)
    options: list[dict[str, Any]] = Field(default_factory=list)  # options.final, in presentation order
    pending_actions: list[dict[str, Any]] = Field(default_factory=list)
    decision: dict[str, Any] | None = None
    executed_actions: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    message_count: int = 0
    llm_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    event_count: int = 0
    last_event_id: str | None = None
    started_at: str | None = None
    ended_at: str | None = None


def is_terminal(event: Event) -> bool:
    """The last event of a run: completed (approved, rejected or a single-agent turn) or a fatal error."""
    return event.type == "run.completed" or (event.type == "run.error" and bool(event.payload.get("fatal")))


def run_snapshot(events: list[Event], run_id: str = "") -> RunSnapshot:
    """Fold events into the current state of the run."""
    snap = RunSnapshot(run_id=events[0].run_id if events else run_id)
    actions: dict[str, dict[str, Any]] = {}
    for event in events:
        p = event.payload
        t = event.type
        if t == "run.started":
            snap.kind = p.get("kind", "full")
            snap.context = p.get("context", {})
            snap.model, snap.model_light = p.get("model"), p.get("model_light")
            snap.started_at = event.ts
        elif t == "stage.started":
            snap.stage = p["stage"]
        elif t == "stage.completed":
            snap.stages_completed.append(p["stage"])
            if p["stage"] == "debate":
                snap.debate = {"rounds": p.get("rounds"), "stop_reason": p.get("stop_reason")}
        elif t == "stance.changed":
            snap.stances[p["agent"]] = p["to"]
        elif t == "options.final":
            snap.options = p.get("options", [])
            snap.stances.update(p.get("stances", {}))
        elif t == "action.proposed":
            actions[p["action_id"]] = dict(p)
        elif t == "approval.requested":
            snap.state = "awaiting_approval"
        elif t == "approval.granted":
            snap.decision = dict(p)
            for action_id, action in actions.items():
                action["status"] = "approved" if action_id in p.get("approved_action_ids", []) else "not_approved"
        elif t == "approval.rejected":
            snap.decision = dict(p)
        elif t == "action.executed":
            snap.executed_actions.append(dict(p))
            if p["action_id"] in actions:
                actions[p["action_id"]]["status"] = "executed"
        elif t == "message.posted":
            snap.message_count += 1
        elif t == "llm.call":
            snap.llm_calls += 1
            snap.prompt_tokens += int(p.get("prompt_tokens", 0))
            snap.completion_tokens += int(p.get("completion_tokens", 0))
        elif t == "run.error":
            snap.errors.append(dict(p))
            if p.get("fatal"):
                snap.state = "failed"
                snap.ended_at = event.ts
        elif t == "run.completed":
            snap.state = "rejected" if p.get("status") == "rejected" else "completed"
            snap.ended_at = event.ts
    snap.pending_actions = list(actions.values())
    snap.event_count = len(events)
    snap.last_event_id = events[-1].event_id if events else None
    return snap
