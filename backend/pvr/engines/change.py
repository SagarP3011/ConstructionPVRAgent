"""Change engine: change types, run context validation, change request and drawing comparison."""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel

from pvr.engines.common import EngineError, r2
from pvr.models import (
    ChangeType,
    ContractorPvr,
    DrawingRevision,
    Mode,
    Overrides,
    ProjectData,
    RunContext,
    VariationInstruction,
)


class ParameterValue(BaseModel):
    name: str
    label: str
    value: float
    default: float
    min: float
    max: float
    step: float


class ChangeRequest(BaseModel):
    """Structured change request for one run."""

    id: str
    change_type: str
    title: str
    element: str
    mode: Mode
    parameters: list[ParameterValue]
    fixed: dict[str, float]
    instruction_text: str
    variation_instruction: VariationInstruction | None = None
    contractor_pvr: ContractorPvr | None = None


class ParameterChange(BaseModel):
    parameter: str
    old: float
    new: float
    unit: str
    note: str = ""


class DrawingComparison(BaseModel):
    """Key parameter changes for the element (drawing revisions for the wall)."""

    change_type: str
    element: str
    drawing: str
    from_revision: str
    to_revision: str | None
    to_revision_note: str
    changes: list[ParameterChange]
    geometry: dict[str, Any]


def list_change_types(data: ProjectData) -> list[ChangeType]:
    """All change types from `scenario.json`, with parameters, defaults, ranges and modes."""
    return list(data.scenario.change_types)


def _on_step(value: float, spec_min: float, step: float) -> bool:
    steps = (value - spec_min) / step
    return abs(steps - round(steps)) < 1e-6


def is_default(ctx: RunContext, data: ProjectData) -> bool:
    """True when every parameter is at its default value."""
    ct = data.change_type(ctx.change_type)
    return all(abs(ctx.parameters[p.name] - p.default) < 1e-9 for p in ct.parameters)


def contractor_claim_applies(ctx: RunContext) -> bool:
    """The contractor claim is checked only in contractor_pvr mode (allowed only at the default)."""
    return ctx.mode == "contractor_pvr"


def validate_context(ctx: RunContext, data: ProjectData) -> None:
    """Reject unknown change types, missing, unknown, out-of-range or off-step parameters and invalid modes."""
    try:
        ct = data.change_type(ctx.change_type)
    except KeyError as exc:
        raise EngineError(str(exc.args[0])) from None

    expected = {p.name for p in ct.parameters}
    unknown = set(ctx.parameters) - expected
    if unknown:
        raise EngineError(f"Unknown parameter(s) for {ct.id}: {', '.join(sorted(unknown))}")
    for p in ct.parameters:
        if p.name not in ctx.parameters:
            raise EngineError(f"Missing parameter for {ct.id}: {p.name}")
        value = ctx.parameters[p.name]
        if not math.isfinite(value) or value < p.min - 1e-9 or value > p.max + 1e-9:
            raise EngineError(f"{p.label} must be between {p.min:g} and {p.max:g}; got {value:g}")
        if not _on_step(value, p.min, p.step):
            raise EngineError(f"{p.label} must be in steps of {p.step:g} from {p.min:g}; got {value:g}")

    if ctx.mode not in ct.modes:
        raise EngineError(f"Mode {ctx.mode} is not available for {ct.id}")
    if ctx.mode == "contractor_pvr" and not (ct.has_contractor_claim_at_default and is_default(ctx, data)):
        raise EngineError("Contractor PVR mode is only available at the default parameter values")

    o = ctx.overrides
    if o.time_buffer_working_days is not None and o.time_buffer_working_days < 0:
        raise EngineError("Time buffer override must be zero or more working days")
    if o.cost_contingency_remaining_aed is not None and not math.isfinite(o.cost_contingency_remaining_aed):
        raise EngineError("Cost contingency override must be a number")


def make_context(
    data: ProjectData,
    change_type: str,
    parameters: dict[str, float] | None = None,
    mode: Mode = "internal_what_if",
    overrides: Overrides | None = None,
) -> RunContext:
    """Build and validate a RunContext. Missing parameters take their defaults."""
    try:
        ct = data.change_type(change_type)
    except KeyError as exc:
        raise EngineError(str(exc.args[0])) from None
    values = {p.name: p.default for p in ct.parameters}
    values.update({k: float(v) for k, v in (parameters or {}).items()})
    ctx = RunContext(change_type=change_type, parameters=values, mode=mode, overrides=overrides or Overrides())
    validate_context(ctx, data)
    return ctx


def _decimals(step: float) -> int:
    return max(0, -math.floor(math.log10(step))) if step < 1 else 0


def current_value_key(parameter_name: str) -> str:
    """The `fixed` key holding today's value of a parameter that sets a new size:
    "new_height_m" -> "current_height_m". Parameters that already are an amount of change (extra width,
    added area) have none."""
    return "current_" + parameter_name.removeprefix("new_")


def resolve_parameter(ct: ChangeType, name: str, value: float | None = None,
                      increase_by: float | None = None) -> float:
    """A parameter value from a request: either the value itself, or an increase on today's value
    (for example "half a metre higher"). The addition is done here, never by a language model."""
    spec = next((p for p in ct.parameters if p.name == name), None)
    if spec is None:
        raise EngineError(f"{ct.id} has no parameter {name}; its parameters are "
                          + ", ".join(p.name for p in ct.parameters))
    if (value is None) == (increase_by is None):
        raise EngineError(f"Give either a value or an increase for {name}, not both or neither")
    if value is not None:
        return float(value)
    current = ct.fixed.get(current_value_key(name))
    if current is None:
        raise EngineError(f"{spec.label} is already an amount of change; give the amount as a value")
    return r2(float(current) + float(increase_by))  # type: ignore[arg-type]


def format_parameter(value: float, step: float) -> str:
    """Format a parameter value with as many decimals as its step needs (2.5, 1.0, 600)."""
    return f"{value:.{_decimals(step)}f}"


def get_change_request(ctx: RunContext, data: ProjectData, sequence: int = 1) -> ChangeRequest:
    """Structured change request; adds VI-017 and PVR-023 in contractor PVR mode."""
    validate_context(ctx, data)
    ct = data.change_type(ctx.change_type)
    text = ct.default_instruction.format(
        **{p.name: format_parameter(ctx.parameters[p.name], p.step) for p in ct.parameters}
    )
    claim = contractor_claim_applies(ctx)
    return ChangeRequest(
        id=f"CR-{ct.id}-{sequence}",
        change_type=ct.id,
        title=ct.title,
        element=ct.element,
        mode=ctx.mode,
        parameters=[
            ParameterValue(
                name=p.name, label=p.label, value=ctx.parameters[p.name],
                default=p.default, min=p.min, max=p.max, step=p.step,
            )
            for p in ct.parameters
        ],
        fixed=dict(ct.fixed),
        instruction_text=text,
        variation_instruction=data.documents.variation_instruction if claim else None,
        contractor_pvr=data.documents.contractor_pvr if claim else None,
    )


def wall_revisions(data: ProjectData) -> tuple[DrawingRevision, DrawingRevision]:
    """(contract revision, current revision) of the boundary wall drawing, by date."""
    revs = sorted(data.documents.drawing_register, key=lambda r: r.date)
    current = [r for r in revs if r.status == "current"]
    return revs[0], (current[-1] if current else revs[-1])


def compare_drawing_revisions(ctx: RunContext, data: ProjectData) -> DrawingComparison:
    """Wall: key data changes from the contract drawing revision to the requested height.
    Road and paving: element geometry and the parameter change."""
    validate_context(ctx, data)
    ct = data.change_type(ctx.change_type)
    p = ctx.parameters

    if ct.id == "wall_height":
        base, current = wall_revisions(data)
        new_h = p["new_height_m"]
        matches_current = abs(current.key_data.wall_height_m - new_h) < 1e-9
        return DrawingComparison(
            change_type=ct.id,
            element=ct.element,
            drawing=base.drawing,
            from_revision=base.revision,
            to_revision=current.revision if matches_current else None,
            to_revision_note=(current.revision_note or "") if matches_current
            else "What-if height: no issued drawing revision at this height.",
            changes=[ParameterChange(parameter="wall_height_m", old=base.key_data.wall_height_m, new=new_h, unit="m")],
            geometry=base.key_data.model_dump(),
        )

    if ct.id == "road_widening":
        g = data.documents.element_geometry.internal_road
        return DrawingComparison(
            change_type=ct.id,
            element=ct.element,
            drawing=g.drawing,
            from_revision=g.revision,
            to_revision=None,
            to_revision_note=g.note,
            changes=[
                ParameterChange(
                    parameter="formation_width_m",
                    old=g.formation_width_m,
                    new=r2(g.formation_width_m + p["widen_by_m"]),
                    unit="m",
                    note=f"over {format_parameter(p['length_m'], 1)} m of the {format_parameter(g.length_m, 1)} m road",
                )
            ],
            geometry=g.model_dump(),
        )

    if ct.id == "paving_area":
        g = data.documents.element_geometry.hardscape
        return DrawingComparison(
            change_type=ct.id,
            element=ct.element,
            drawing=g.drawing,
            from_revision=g.revision,
            to_revision=None,
            to_revision_note=g.note,
            changes=[
                ParameterChange(
                    parameter="interlocking_paving_area_m2",
                    old=g.interlocking_paving_area_m2,
                    new=r2(g.interlocking_paving_area_m2 + p["added_area_m2"]),
                    unit="m2",
                )
            ],
            geometry=g.model_dump(),
        )

    raise EngineError(f"No drawing comparison rule for change type {ct.id}")
