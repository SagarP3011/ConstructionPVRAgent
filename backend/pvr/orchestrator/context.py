"""Run session: the RunContext plus the run's shared state (facts, blackboard, events, messages)."""

from __future__ import annotations

from dataclasses import dataclass, field

from pvr.config import Settings
from pvr.events.bus import EventBus
from pvr.ids import IdGen
from pvr.models import AgentMessage, ProjectData, RunContext
from pvr.orchestrator.blackboard import Blackboard
from pvr.tools.facts import FactRegistry

__all__ = ["RunContext", "RunSession"]


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
