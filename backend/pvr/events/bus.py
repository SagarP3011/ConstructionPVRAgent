"""Event bus: every event of a run goes through here to its sinks (trace file, console, SSE streams)."""

from __future__ import annotations

import threading
from typing import Any, Callable

from pvr.ids import IdGen, now_iso
from pvr.models import Event

Sink = Callable[[Event], None]


class EventBus:
    """Creates events with sequential ids and passes each one to every sink. Keeps them in memory too.
    Thread-safe: agents in the same stage may emit concurrently; events keep one total order."""

    def __init__(self, run_id: str, ids: IdGen, sinks: list[Sink] | None = None) -> None:
        self.run_id = run_id
        self._ids = ids
        self._sinks: list[Sink] = list(sinks or [])
        self._lock = threading.RLock()
        self.events: list[Event] = []

    def add_sink(self, sink: Sink) -> None:
        with self._lock:
            self._sinks.append(sink)

    def subscribe(self, sink: Sink) -> list[Event]:
        """Add a sink and return the events so far, atomically: the subscriber sees every event exactly
        once, the history from the returned list and everything later through the sink."""
        with self._lock:
            self._sinks.append(sink)
            return list(self.events)

    def history(self) -> list[Event]:
        """A copy of the events so far."""
        with self._lock:
            return list(self.events)

    def remove_sink(self, sink: Sink) -> None:
        with self._lock:
            if sink in self._sinks:
                self._sinks.remove(sink)

    def emit(self, type_: str, payload: dict[str, Any] | None = None) -> Event:
        with self._lock:
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
        with self._lock:
            return [e for e in self.events if e.type == type_]
