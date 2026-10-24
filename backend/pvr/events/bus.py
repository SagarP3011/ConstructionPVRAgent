"""Event bus: every event of a run goes through here to its sinks (trace file now, SSE in Phase 4)."""

from __future__ import annotations

from typing import Any, Callable

from pvr.ids import IdGen, now_iso
from pvr.models import Event

Sink = Callable[[Event], None]


class EventBus:
    """Creates events with sequential ids and passes each one to every sink. Keeps them in memory too."""

    def __init__(self, run_id: str, ids: IdGen, sinks: list[Sink] | None = None) -> None:
        self.run_id = run_id
        self._ids = ids
        self._sinks: list[Sink] = list(sinks or [])
        self.events: list[Event] = []

    def add_sink(self, sink: Sink) -> None:
        self._sinks.append(sink)

    def emit(self, type_: str, payload: dict[str, Any] | None = None) -> Event:
        event = Event(
            event_id=self._ids.next("E", width=6), run_id=self.run_id, type=type_, ts=now_iso(),
            payload=payload or {},
        )
        self.events.append(event)
        for sink in self._sinks:
            sink(event)
        return event

    def of_type(self, type_: str) -> list[Event]:
        """Events of one type, in order."""
        return [e for e in self.events if e.type == type_]
