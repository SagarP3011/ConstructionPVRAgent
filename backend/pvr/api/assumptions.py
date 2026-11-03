"""Read-only "Rates and assumptions" endpoints for the start screen.

Display only. These routes read the data files and the illustrative crew file `assumptions/crews.json`, and call
the existing deterministic engines unchanged. They never call a language model, never write a file and are not
used by any agent, tool or run. To remove the feature: delete this module, `assumptions/crews.json`, the
`include_router` line in `pvr/api/main.py` and the frontend tab.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from pvr.config import REPO_ROOT
from pvr.engines.change import make_context, wall_revisions
from pvr.engines.common import EngineError
from pvr.engines.cost import RATE_SOURCE, price_change
from pvr.engines.cpm import run_cpm
from pvr.engines.options import PARETO_RULE, eligible_activities, evaluate_option
from pvr.engines.productivity import added_duration
from pvr.engines.quantities import quantify_change
from pvr.models import ProjectData

CREWS_PATH = REPO_ROOT / "assumptions" / "crews.json"
CREWS_SOURCE = "assumptions/crews.json"

# Plain descriptions of what the engines do (the rules themselves live in the engine code named in `source`).
DELAY_RULE = (
    "Delay = completion working day with the change, minus the contract completion working day "
    "(never below 0). Float on an activity absorbs added days until it runs out."
)
BUFFER_RULE = (
    "Time buffer left = time buffer - delay. Contingency left = remaining contingency - total cost of the option."
)
TOTAL_COST_RULE = "Total cost = direct cost + additional crew cost + time-related cost (per working day of delay)."

router = APIRouter()


# --- crew file ---------------------------------------------------------------------------------------------


class Trade(BaseModel):
    trade: str
    count: int


class Crew(BaseModel):
    activity_id: str
    crew_name: str
    hours_per_day: float
    trades: list[Trade]
    equipment: list[str]


class CrewFile(BaseModel):
    status: str
    note: str
    crews: list[Crew]


@lru_cache(maxsize=1)
def load_crews() -> CrewFile:
    """The illustrative crew file, validated."""
    with CREWS_PATH.open(encoding="utf-8") as f:
        return CrewFile.model_validate(json.load(f))


def _people(crew: Crew) -> int:
    return sum(t.count for t in crew.trades)


def labour_hours_per_unit(crew: Crew, output_per_crew_day: float) -> float:
    """People in the crew x hours per day / output per crew-day, to 3 decimals."""
    return round(_people(crew) * crew.hours_per_day / output_per_crew_day, 3)


# --- static assumptions ------------------------------------------------------------------------------------


def _work_rates(data: ProjectData) -> dict[str, Any]:
    acts = {a.id: a for a in data.schedule.activities}
    items = []
    for p in data.productivity.items:
        boq = data.boq_item(p.boq_code)
        act = acts[p.activity_id]
        items.append({
            "boq_code": p.boq_code, "description": boq.description, "unit": p.unit, "rate_aed": boq.rate_aed,
            "activity_id": act.id, "activity_name": act.name, "baseline_duration": act.duration,
            "output_per_crew_day": p.productivity,
        })
    return {"units": data.productivity.units, "rule": data.productivity.rule, "items": items,
            "source": "data/productivity.json, data/boq.json, data/schedule.json"}


def _crews(data: ProjectData) -> dict[str, Any]:
    crew_file = load_crews()
    acts = {a.id: a for a in data.schedule.activities}
    items = []
    for crew in crew_file.crews:
        rates = [p for p in data.productivity.items if p.activity_id == crew.activity_id]
        items.append({
            "activity_id": crew.activity_id,
            "activity_name": acts[crew.activity_id].name,
            "crew_name": crew.crew_name,
            "trades": [t.model_dump() for t in crew.trades],
            "people": _people(crew),
            "hours_per_day": crew.hours_per_day,
            "equipment": crew.equipment,
            "work_items": [
                {"boq_code": p.boq_code, "unit": p.unit, "output_per_crew_day": p.productivity,
                 "labour_hours_per_unit": labour_hours_per_unit(crew, p.productivity)}
                for p in rates
            ],
        })
    return {"status": crew_file.status, "note": crew_file.note, "items": items, "source": CREWS_SOURCE}


def _clauses(data: ProjectData, keys: list[str]) -> list[dict[str, str]]:
    refs = data.commercial.contract_clause_refs
    by_number = {c.clause: c for c in data.contract.clauses}
    return [by_number[refs[k]].model_dump() for k in keys if refs.get(k) in by_number]


def _cost(data: ProjectData) -> dict[str, Any]:
    c = data.commercial
    crew = c.additional_crew
    return {
        "rate_source": RATE_SOURCE,
        "direct_cost_rule": "Direct cost of each changed line = quantity change x contract BOQ rate.",
        "time_related_cost_per_working_day_aed": c.time_related_cost_per_working_day_aed,
        "additional_crew": {
            "mobilisation_aed_per_crew_per_activity": crew.mobilisation_aed_per_crew_per_activity,
            "day_rate_aed": crew.day_rate_aed,
            "max_additional_crews_per_activity": crew.max_additional_crews_per_activity,
            "rule": crew.rule,
            "eligible_activities_by_change_type": crew.eligible_activities_by_change_type,
        },
        "cost_contingency_remaining_aed": data.project.cost_contingency_remaining_aed,
        "total_cost_rule": TOTAL_COST_RULE,
        "clauses": _clauses(data, ["valuation", "preliminaries", "time_related_costs", "acceleration"]),
        "source": "data/commercial.json, data/project.json, data/contract.json",
    }


def _time(data: ProjectData) -> dict[str, Any]:
    p = data.project
    cpm = run_cpm(data)
    return {
        "calendar": p.calendar.model_dump(mode="json"),
        "data_date": p.data_date.isoformat(),
        "data_date_working_day": p.data_date_working_day,
        "contract_completion_working_day": p.contract_completion_working_day,
        "contract_completion_date": p.contract_completion_date.isoformat(),
        "employer_commitment_working_day": p.employer_commitment_working_day,
        "employer_commitment_date": p.employer_commitment_date.isoformat(),
        "time_buffer_working_days": p.time_buffer_working_days,
        "added_duration_rule": data.productivity.rule,
        "additional_crew_rule": data.commercial.additional_crew.rule,
        "delay_rule": DELAY_RULE,
        "buffer_rule": BUFFER_RULE,
        "pareto_rule": PARETO_RULE,
        "baseline_completion_working_day": cpm.completion_working_day,
        "baseline_completion_date": cpm.completion_date.isoformat(),
        "baseline_critical_path": cpm.critical_path,
        "activities": [
            {"activity_id": t.activity_id, "name": t.name, "duration": t.duration, "early_start": t.ES,
             "early_finish": t.EF, "total_float": t.TF, "critical": t.critical}
            for t in cpm.activities.values()
        ],
        "clauses": _clauses(data, ["extension_of_time", "time_related_costs"]),
        "source": "data/project.json, data/schedule.json, data/productivity.json, data/commercial.json "
                  "(critical path from the CPM engine)",
    }


def _geometry(data: ProjectData, element: str) -> dict[str, Any]:
    g = data.documents.element_geometry
    if element == "boundary_wall":
        base, _ = wall_revisions(data)
        return {"drawing": base.drawing, "revision": base.revision, **base.key_data.model_dump(mode="json")}
    if element == "internal_road":
        return g.internal_road.model_dump(mode="json")
    if element == "hardscape":
        return g.hardscape.model_dump(mode="json")
    return {}


def _quantity_rules(data: ProjectData) -> list[dict[str, Any]]:
    rules = []
    for ct in data.scenario.change_types:
        q = quantify_change(make_context(data, ct.id), data)
        rules.append({
            "change_type": ct.id, "title": ct.title, "element": ct.element,
            "parameters": [p.model_dump() for p in ct.parameters], "fixed": ct.fixed,
            "geometry": _geometry(data, ct.element),
            "lines": [{"code": line.code, "description": line.description, "unit": line.unit, "basis": line.basis}
                      for line in q.lines],
            "unaffected": [u.model_dump() for u in q.unaffected],
            "requires_review": [r.model_dump() for r in q.requires_review],
        })
    return rules


def build_assumptions(data: ProjectData) -> dict[str, Any]:
    """Everything the Rates and assumptions tab shows that does not depend on the selected change."""
    return {
        "work_rates": _work_rates(data),
        "crews": _crews(data),
        "cost": _cost(data),
        "time": _time(data),
        "quantity_rules": _quantity_rules(data),
        "quantity_rules_source": "data/documents.json, data/scenario.json (rules from the quantity engine)",
    }


# --- worked example ----------------------------------------------------------------------------------------


def build_example(data: ProjectData, change_type: str, parameters: dict[str, float]) -> dict[str, Any]:
    """A worked example for one change and size, made only of existing engine outputs."""
    ctx = make_context(data, change_type, parameters)
    baseline = run_cpm(data)
    q = quantify_change(ctx, data)
    cost = price_change(ctx, data)
    durations = added_duration(ctx, data)
    no_crews = evaluate_option(ctx, data, [])
    with_crew = [evaluate_option(ctx, data, [aid]) for aid in eligible_activities(ctx, data)]
    return {
        "change_type": ctx.change_type,
        "parameters": ctx.parameters,
        "quantities": [line.model_dump() for line in q.changed_lines()],
        "requires_review": [r.model_dump() for r in q.requires_review],
        "cost": cost.model_dump(include={"lines", "direct_cost_aed", "rate_source", "unpriced_items"}),
        "durations": [
            {**a.model_dump(), "baseline_total_float": baseline.activities[a.activity_id].TF}
            for a in durations.activities
        ],
        "contract_completion_working_day": data.project.contract_completion_working_day,
        "baseline_completion_working_day": baseline.completion_working_day,
        "no_extra_crews": no_crews.model_dump(mode="json", include={
            "option_id", "completion_working_day", "completion_date", "delay_working_days", "direct_cost_aed",
            "acceleration_cost_aed", "time_related_cost_aed", "total_cost_aed", "time_buffer_remaining_days",
            "contingency_remaining_aed",
        }),
        "one_extra_crew": [
            {
                "option_id": o.option_id,
                "activity_id": o.accelerated[0].activity_id,
                "duration_before": o.accelerated[0].duration_before,
                "duration_after": o.accelerated[0].duration_after,
                "crew_cost_aed": o.accelerated[0].crew_cost_aed,
                "delay_working_days": o.delay_working_days,
                "total_cost_aed": o.total_cost_aed,
            }
            for o in with_crew
        ],
        "time_related_cost_per_working_day_aed": data.commercial.time_related_cost_per_working_day_aed,
        "source": "Quantity, cost, productivity, CPM and options engines, with the data files",
    }


# --- routes ------------------------------------------------------------------------------------------------


@router.get("/api/assumptions")
def assumptions(request: Request) -> dict[str, Any]:
    """Rates and assumptions behind the cost and time calculations, with the source of each value."""
    return build_assumptions(request.app.state.runs.data)


@router.get("/api/assumptions/example/{change_type}")
def assumptions_example(change_type: str, request: Request) -> dict[str, Any]:
    """Worked example for a change; its sizes come as query parameters (for example `?new_height_m=2.5`)."""
    try:
        parameters = {k: float(v) for k, v in request.query_params.items()}
    except ValueError:
        raise HTTPException(422, "Sizes must be numbers") from None
    try:
        return build_example(request.app.state.runs.data, change_type, parameters)
    except EngineError as exc:
        raise HTTPException(422, str(exc)) from None
