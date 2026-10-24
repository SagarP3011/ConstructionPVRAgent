"""Options engine: evaluate acceleration options and find the Pareto set (SPEC 7.7, 7.8, 2.4)."""

from __future__ import annotations

from datetime import date
from itertools import combinations

from pydantic import BaseModel

from pvr.engines.common import EngineError, ceil_tol, r2
from pvr.engines.cost import price_change
from pvr.engines.cpm import run_cpm
from pvr.engines.productivity import added_duration
from pvr.models import ProjectData, RunContext

NO_CREWS_ID = "OPT-NONE"


class AcceleratedActivity(BaseModel):
    activity_id: str
    duration_before: int
    duration_after: int
    crew_cost_aed: float


class OptionResult(BaseModel):
    option_id: str
    extra_crews_on: list[str]
    accelerated: list[AcceleratedActivity]
    completion_working_day: int
    completion_date: date
    delay_working_days: int
    direct_cost_aed: float
    acceleration_cost_aed: float
    time_related_cost_aed: float
    total_cost_aed: float
    time_buffer_remaining_days: int
    contingency_remaining_aed: float
    critical_path: list[str]


class OptionSearch(BaseModel):
    change_type: str
    eligible_activities: list[str]
    options: list[OptionResult]
    pareto_option_ids: list[str]
    pareto_rule: str

    def pareto(self) -> list[OptionResult]:
        """Pareto options in presentation order (delay, then cost)."""
        by_id = {o.option_id: o for o in self.options}
        return [by_id[i] for i in self.pareto_option_ids]


PARETO_RULE = (
    "Keep options that no other option beats on both total cost and delay. "
    "Ties on both keep the option with fewer extra crews, then the one whose activities come first "
    "in schedule order. Ordered by delay, then cost."
)


def time_buffer_days(ctx: RunContext, data: ProjectData) -> int:
    """Employer's time buffer in working days (override if given)."""
    o = ctx.overrides.time_buffer_working_days
    return data.project.time_buffer_working_days if o is None else o


def contingency_aed(ctx: RunContext, data: ProjectData) -> float:
    """Remaining cost contingency in AED (override if given)."""
    o = ctx.overrides.cost_contingency_remaining_aed
    return data.project.cost_contingency_remaining_aed if o is None else o


def _schedule_index(data: ProjectData) -> dict[str, int]:
    return {a.id: i for i, a in enumerate(data.schedule.activities)}


def eligible_activities(ctx: RunContext, data: ProjectData) -> list[str]:
    """Activities that may receive an extra crew for this change type, in schedule order."""
    eligible = data.commercial.additional_crew.eligible_activities_by_change_type.get(ctx.change_type, [])
    index = _schedule_index(data)
    return sorted(eligible, key=lambda a: index[a])


def option_id(extra_crews_on: list[str], data: ProjectData) -> str:
    """`OPT-NONE`, or `OPT-` plus activity ids in schedule order joined by `-`."""
    if not extra_crews_on:
        return NO_CREWS_ID
    index = _schedule_index(data)
    return "OPT-" + "-".join(sorted(extra_crews_on, key=lambda a: index[a]))


def parse_option_id(option: str, data: ProjectData) -> list[str]:
    """Activity ids from an option id. Raises EngineError for an unknown format or activity."""
    if option == NO_CREWS_ID:
        return []
    if not option.startswith("OPT-") or len(option) <= 4:
        raise EngineError(f"Not an option id: {option}")
    crews = option[4:].split("-")
    index = _schedule_index(data)
    unknown = [a for a in crews if a not in index]
    if unknown:
        raise EngineError(f"Unknown activity in option id {option}: {', '.join(unknown)}")
    return crews


def evaluate_option(ctx: RunContext, data: ProjectData, extra_crews_on: list[str]) -> OptionResult:
    """Accelerate the listed activities (one extra crew each), run CPM and cost the option."""
    eligible = eligible_activities(ctx, data)
    max_crews = data.commercial.additional_crew.max_additional_crews_per_activity
    for aid in set(extra_crews_on):
        if extra_crews_on.count(aid) > max_crews:
            raise EngineError(f"No more than {max_crews} extra crew per activity ({aid} listed more than once)")
    not_eligible = [a for a in extra_crews_on if a not in eligible]
    if not_eligible:
        raise EngineError(
            f"Not eligible for an extra crew on {ctx.change_type}: {', '.join(not_eligible)}. "
            f"Eligible: {', '.join(eligible)}"
        )

    crew = data.commercial.additional_crew
    baseline = {a.id: a.duration for a in data.schedule.activities}
    durations = added_duration(ctx, data).new_durations()
    index = _schedule_index(data)
    accelerated = []
    for aid in sorted(extra_crews_on, key=lambda a: index[a]):
        before = durations.get(aid, baseline[aid])
        after = ceil_tol(before / 2)
        durations[aid] = after
        accelerated.append(AcceleratedActivity(
            activity_id=aid, duration_before=before, duration_after=after,
            crew_cost_aed=r2(crew.mobilisation_aed_per_crew_per_activity + crew.day_rate_aed * after),
        ))

    cpm = run_cpm(data, durations)
    delay = max(0, cpm.completion_working_day - data.project.contract_completion_working_day)
    direct = price_change(ctx, data).direct_cost_aed
    acceleration = r2(sum(a.crew_cost_aed for a in accelerated))
    time_related = r2(data.commercial.time_related_cost_per_working_day_aed * delay)
    total = r2(direct + acceleration + time_related)
    return OptionResult(
        option_id=option_id(extra_crews_on, data),
        extra_crews_on=[a.activity_id for a in accelerated],
        accelerated=accelerated,
        completion_working_day=cpm.completion_working_day,
        completion_date=cpm.completion_date,
        delay_working_days=delay,
        direct_cost_aed=direct,
        acceleration_cost_aed=acceleration,
        time_related_cost_aed=time_related,
        total_cost_aed=total,
        time_buffer_remaining_days=time_buffer_days(ctx, data) - delay,
        contingency_remaining_aed=r2(contingency_aed(ctx, data) - total),
        critical_path=cpm.critical_path,
    )


def _dominates(a: OptionResult, b: OptionResult) -> bool:
    """a is at least as good as b on cost and delay, and strictly better on one."""
    no_worse = a.total_cost_aed <= b.total_cost_aed and a.delay_working_days <= b.delay_working_days
    better = a.total_cost_aed < b.total_cost_aed or a.delay_working_days < b.delay_working_days
    return no_worse and better


def pareto_ids(options: list[OptionResult], data: ProjectData) -> list[str]:
    """Pareto set by the rule in SPEC 2.4, ordered by delay then cost."""
    index = _schedule_index(data)
    front = [o for o in options if not any(_dominates(p, o) for p in options)]
    kept: dict[tuple[int, float], OptionResult] = {}
    for o in sorted(front, key=lambda o: (len(o.extra_crews_on), [index[a] for a in o.extra_crews_on])):
        kept.setdefault((o.delay_working_days, o.total_cost_aed), o)
    return [o.option_id for o in sorted(kept.values(), key=lambda o: (o.delay_working_days, o.total_cost_aed))]


def search_options(ctx: RunContext, data: ProjectData) -> OptionSearch:
    """Evaluate every combination of eligible activities and return all options plus the Pareto set."""
    eligible = eligible_activities(ctx, data)
    options = [
        evaluate_option(ctx, data, list(combo))
        for size in range(len(eligible) + 1)
        for combo in combinations(eligible, size)
    ]
    return OptionSearch(
        change_type=ctx.change_type,
        eligible_activities=eligible,
        options=options,
        pareto_option_ids=pareto_ids(options, data),
        pareto_rule=PARETO_RULE,
    )
