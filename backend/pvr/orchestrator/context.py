"""Run session: the RunContext plus the run's shared state (facts, blackboard, events, messages)."""

from __future__ import annotations

import threading
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from pydantic import BaseModel, Field

from pvr.config import Settings
from pvr.events.bus import EventBus
from pvr.ids import IdGen
from pvr.models import AgentMessage, ProjectData, RunContext
from pvr.orchestrator.blackboard import Blackboard
from pvr.tools.facts import FactRegistry

if TYPE_CHECKING:
    from pvr.tools.registry import ToolOutcome

__all__ = ["RunContext", "RunSession", "TurnState", "PendingAction", "current_turn"]


class TurnState(BaseModel):
    """The agent turn running in this thread (set by the agent runtime)."""

    agent: str
    depth: int = 0  # 0 = a normal turn, 1 = an answer turn for ask_agent
    asks: int = 0


current_turn: ContextVar[TurnState | None] = ContextVar("current_turn", default=None)


class PendingAction(BaseModel):
    action_id: str
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    reason: str
    proposed_by: str
    status: str = "pending"  # pending, approved, not_approved, executed


AskHandler = Callable[[str, str, str], dict[str, Any]]
ToolHook = Callable[["ToolOutcome"], None]


@dataclass
class RunSession:
    """Everything one run owns. Tools receive it; agents never see it directly."""

    run_id: str
    ctx: RunContext
    data: ProjectData
    settings: Settings
    ids: IdGen
    bus: EventBus
    facts: FactRegistry = field(default_factory=FactRegistry)
    blackboard: Blackboard = field(default_factory=Blackboard)
    messages: list[AgentMessage] = field(default_factory=list)
    stage: str = "intake"
    round: int = 0
    evaluated_options: dict[str, dict[str, Any]] = field(default_factory=dict)
    pending_actions: list[PendingAction] = field(default_factory=list)
    ask_handler: AskHandler | None = None
    tool_hooks: list[ToolHook] = field(default_factory=list)
    run_dir: Path | None = None  # runs/<run_id>; None in tests that write nothing
    lock: threading.RLock = field(default_factory=threading.RLock)

    def add_message(self, message: AgentMessage) -> None:
        with self.lock:
            self.messages.append(message)

    def message(self, message_id: str) -> AgentMessage:
        with self.lock:
            return next(m for m in self.messages if m.message_id == message_id)
