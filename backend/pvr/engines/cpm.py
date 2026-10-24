"""Critical path method: forward and backward pass over FS and SS relationships with lags.

Day convention (SPEC 6): working days are integers from 0. An activity with early
start ES and duration d occupies days ES..ES+d-1 and has EF = ES + d. The
completion date of a finish EF is the calendar date of working day EF - 1.
"""

from __future__ import annotations

from datetime import date, timedelta

import networkx as nx
from pydantic import BaseModel

from pvr.engines.common import EngineError
from pvr.models import Activity, Calendar, ProjectData

_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


class ActivityTiming(BaseModel):
    activity_id: str
    name: str
    duration: int
    ES: int
    EF: int
    LS: int
    LF: int
    TF: int
    critical: bool
    start_date: date
    finish_date: date


class CpmResult(BaseModel):
    completion_working_day: int
    completion_date: date
    critical_path: list[str]
    activities: dict[str, ActivityTiming]


def working_day_to_date(day: int, calendar: Calendar) -> date:
    """Calendar date of a working day number (day 0 is the calendar start date)."""
    if day < 0:
        raise EngineError("Working day must be zero or more")
    working = set(calendar.working_days)
    holidays = set(calendar.holidays)

    def is_working(d: date) -> bool:
        return _WEEKDAYS[d.weekday()] in working and d not in holidays

    current = calendar.start_date
    while not is_working(current):
        current += timedelta(days=1)
    for _ in range(day):
        current += timedelta(days=1)
        while not is_working(current):
            current += timedelta(days=1)
    return current


def finish_date(ef: int, calendar: Calendar) -> date:
    """Completion date of a finish EF: the date of working day EF - 1 (day 0 for EF 0)."""
    return working_day_to_date(max(ef - 1, 0), calendar)


def _graph(activities: list[Activity]) -> nx.DiGraph:
    ids = {a.id for a in activities}
    g = nx.DiGraph()
    g.add_nodes_from(ids)
    for a in activities:
        for rel in a.predecessors:
            if rel.id not in ids:
                raise EngineError(f"Activity {a.id} has unknown predecessor {rel.id}")
            g.add_edge(rel.id, a.id)
    if not nx.is_directed_acyclic_graph(g):
        cycle = nx.find_cycle(g)
        raise EngineError("Schedule has a cycle: " + " -> ".join(u for u, _ in cycle))
    return g


def run_cpm(data: ProjectData, duration_overrides: dict[str, int] | None = None) -> CpmResult:
    """Forward and backward pass. Returns completion, critical path (TF 0, schedule order) and timings."""
    overrides = duration_overrides or {}
    activities = data.schedule.activities
    by_id = {a.id: a for a in activities}
    unknown = set(overrides) - set(by_id)
    if unknown:
        raise EngineError(f"Unknown activity id(s): {', '.join(sorted(unknown))}")
    if any(d < 0 for d in overrides.values()):
        raise EngineError("Durations must be zero or more")
    dur = {a.id: overrides.get(a.id, a.duration) for a in activities}
    order = list(nx.topological_sort(_graph(activities)))

    es: dict[str, int] = {}
    for aid in order:
        start = 0
        for rel in by_id[aid].predecessors:
            anchor = es[rel.id] + dur[rel.id] if rel.type == "FS" else es[rel.id]
            start = max(start, anchor + rel.lag)
        es[aid] = start
    ef = {aid: es[aid] + dur[aid] for aid in order}
    completion = max(ef.values())

    successors: dict[str, list[tuple[str, str, int]]] = {aid: [] for aid in order}
    for a in activities:
        for rel in a.predecessors:
            successors[rel.id].append((a.id, rel.type, rel.lag))
    lf: dict[str, int] = {}
    ls: dict[str, int] = {}
    for aid in reversed(order):
        finish = completion
        for succ, rel_type, lag in successors[aid]:
            # FS: EF + lag <= LS(succ).  SS: ES + lag <= LS(succ), i.e. LF <= LS(succ) - lag + duration.
            limit = ls[succ] - lag if rel_type == "FS" else ls[succ] - lag + dur[aid]
            finish = min(finish, limit)
        lf[aid] = finish
        ls[aid] = finish - dur[aid]

    cal = data.project.calendar
    timings = {
        a.id: ActivityTiming(
            activity_id=a.id, name=a.name, duration=dur[a.id],
            ES=es[a.id], EF=ef[a.id], LS=ls[a.id], LF=lf[a.id], TF=ls[a.id] - es[a.id],
            critical=ls[a.id] == es[a.id],
            start_date=working_day_to_date(es[a.id], cal), finish_date=finish_date(ef[a.id], cal),
        )
        for a in activities
    }
    return CpmResult(
        completion_working_day=completion,
        completion_date=finish_date(completion, cal),
        critical_path=[a.id for a in activities if timings[a.id].critical],
        activities=timings,
    )
