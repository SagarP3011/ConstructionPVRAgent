"""Productivity engine: added duration per activity from the quantity changes (SPEC 7.5)."""

from __future__ import annotations

from pydantic import BaseModel

from pvr.engines.common import ceil_tol, r2
from pvr.engines.quantities import quantify_change
from pvr.models import ProjectData, RunContext


class DurationItem(BaseModel):
    code: str
    delta: float
    productivity_per_day: float
    crew_days: float


class ActivityDuration(BaseModel):
    activity_id: str
    name: str
    baseline_duration: int
    added_days: int
    new_duration: int
    items: list[DurationItem]


class DurationImpact(BaseModel):
    change_type: str
    rule: str
    activities: list[ActivityDuration]
    total_added_days: int

    def new_durations(self) -> dict[str, int]:
        """Activity id -> new duration, for the affected activities."""
        return {a.activity_id: a.new_duration for a in self.activities}


def added_duration(ctx: RunContext, data: ProjectData) -> DurationImpact:
    """Per activity: ceiling(sum over its changed items of delta / productivity). Activities in schedule order."""
    deltas = {line.code: line.delta for line in quantify_change(ctx, data).changed_lines()}
    items_by_activity: dict[str, list[DurationItem]] = {}
    for p in data.productivity.items:
        delta = deltas.get(p.boq_code, 0.0)
        if delta > 0:
            items_by_activity.setdefault(p.activity_id, []).append(
                DurationItem(code=p.boq_code, delta=delta, productivity_per_day=p.productivity,
                             crew_days=r2(delta / p.productivity))
            )

    activities = []
    for act in data.schedule.activities:
        items = items_by_activity.get(act.id)
        if not items:
            continue
        added = ceil_tol(sum(i.delta / i.productivity_per_day for i in items))
        if added == 0:
            continue
        activities.append(ActivityDuration(
            activity_id=act.id, name=act.name, baseline_duration=act.duration,
            added_days=added, new_duration=act.duration + added, items=items,
        ))
    return DurationImpact(
        change_type=ctx.change_type,
        rule=data.productivity.rule,
        activities=activities,
        total_added_days=sum(a.added_days for a in activities),
    )
