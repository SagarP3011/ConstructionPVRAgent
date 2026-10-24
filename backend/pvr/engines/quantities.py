"""Quantity engine: `quantify_change`, one measurement rule per change type (SPEC 7.2)."""

from __future__ import annotations

import math

from pydantic import BaseModel

from pvr.engines.change import validate_context, wall_revisions
from pvr.engines.common import EngineError, r2
from pvr.models import ProjectData, RunContext


class QuantityLine(BaseModel):
    """Old and new measured quantity of one BOQ line. `delta` is zero for unaffected lines."""

    code: str
    description: str
    unit: str
    old: float | None
    new: float | None
    delta: float
    basis: str


class ItemNote(BaseModel):
    code: str
    description: str
    reason: str


class ReviewItem(ItemNote):
    """A related item that cannot be measured from the change alone."""

    needs_new_rate: bool


class QuantityChange(BaseModel):
    change_type: str
    lines: list[QuantityLine]
    unaffected: list[ItemNote]
    requires_review: list[ReviewItem]

    def deltas(self) -> dict[str, float]:
        """BOQ code -> quantity change, for every measured line."""
        return {line.code: line.delta for line in self.lines}

    def changed_lines(self) -> list[QuantityLine]:
        """Lines with a non-zero change."""
        return [line for line in self.lines if line.delta != 0]


def _line(data: ProjectData, code: str, old: float, new: float, basis: str) -> QuantityLine:
    item = data.boq_item(code)
    return QuantityLine(
        code=code, description=item.description, unit=item.unit,
        old=r2(old), new=r2(new), delta=r2(new - old), basis=basis,
    )


def _note(data: ProjectData, code: str, reason: str) -> ItemNote:
    return ItemNote(code=code, description=data.boq_item(code).description, reason=reason)


def _review(data: ProjectData, code: str, reason: str, needs_new_rate: bool) -> ReviewItem:
    return ReviewItem(
        code=code, description=data.boq_item(code).description, reason=reason, needs_new_rate=needs_new_rate,
    )


def _wall(ctx: RunContext, data: ProjectData) -> QuantityChange:
    base, _ = wall_revisions(data)
    k = base.key_data
    h_old, h_new = k.wall_height_m, ctx.parameters["new_height_m"]
    length = k.wall_length_m
    columns = math.floor(length / k.stiffener_column_spacing_m) + 1
    section = k.stiffener_column_section_m[0] * k.stiffener_column_section_m[1]
    faces = k.faces_finished

    lines = [
        _line(data, "B-04-010", length * h_old, length * h_new, "wall length x height"),
        _line(data, "B-04-015", columns * section * h_old, columns * section * h_new,
              "(floor(length / column spacing) + 1) x column section x height"),
        _line(data, "B-04-020", length * h_old * faces, length * h_new * faces, "wall length x height x faces"),
        _line(data, "B-04-040", length * h_old * faces, length * h_new * faces, "wall length x height x faces"),
        _line(data, "B-04-030", length, length, "wall length (coping sits on top of the wall)"),
    ]
    footing = "footing designed for previous wall height; structural check needed"
    return QuantityChange(
        change_type=ctx.change_type,
        lines=lines,
        unaffected=[_note(data, "B-04-030", "coping is measured by wall length, which does not change with height")],
        requires_review=[
            _review(data, "B-04-005", footing, needs_new_rate=False),
            _review(data, "B-04-008", footing, needs_new_rate=False),
        ],
    )


def _road(ctx: RunContext, data: ProjectData) -> QuantityChange:
    g = data.documents.element_geometry.internal_road
    old_area = g.length_m * g.formation_width_m
    added_area = ctx.parameters["widen_by_m"] * ctx.parameters["length_m"]
    markings = data.boq_item("R-02-080")

    lines = [
        _line(data, "R-02-010", old_area * g.excavation_depth_m, (old_area + added_area) * g.excavation_depth_m,
              "road area x excavation depth"),
    ]
    lines += [_line(data, code, old_area, old_area + added_area, f"road area ({layer})")
              for code, layer in g.layers.items()]
    lines.append(_line(data, "R-02-080", markings.quantity, markings.quantity,
                       "road markings follow the road length"))
    return QuantityChange(
        change_type=ctx.change_type,
        lines=lines,
        unaffected=[_note(data, "R-02-080", "road markings follow the road length, which does not change")],
        requires_review=[
            _review(
                data, "R-02-050",
                "kerb line moves over the widened length; removal and re-laying has no BOQ rate, "
                "so a new rate is needed (clause 13.3)",
                needs_new_rate=True,
            )
        ],
    )


def _paving(ctx: RunContext, data: ProjectData) -> QuantityChange:
    g = data.documents.element_geometry.hardscape
    added = ctx.parameters["added_area_m2"]
    lines = [
        _line(data, "L-05-050", g.interlocking_paving_area_m2, g.interlocking_paving_area_m2 + added,
              "interlocking paving area plus the added area"),
        _line(data, "L-05-060", g.granite_paving_area_m2, g.granite_paving_area_m2,
              "granite paving area at entrances"),
    ]
    return QuantityChange(
        change_type=ctx.change_type,
        lines=lines,
        unaffected=[_note(data, "L-05-060", "the added area is interlocking paving; granite paving is not extended")],
        requires_review=[],
    )


_RULES = {"wall_height": _wall, "road_widening": _road, "paving_area": _paving}


def quantify_change(ctx: RunContext, data: ProjectData) -> QuantityChange:
    """Measure the change: old, new and delta per BOQ line, plus unaffected and review items."""
    validate_context(ctx, data)
    rule = _RULES.get(ctx.change_type)
    if rule is None:
        raise EngineError(f"No quantity rule for change type {ctx.change_type}")
    return rule(ctx, data)
