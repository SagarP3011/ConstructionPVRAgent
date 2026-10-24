"""Cost engine: price the change at contract rates and compare a contractor claim (SPEC 7.4, 7.10)."""

from __future__ import annotations

from pydantic import BaseModel

from pvr.engines.change import contractor_claim_applies
from pvr.engines.common import EngineError, bm25_scores, r2
from pvr.engines.contract import NoticeCheck, check_notice
from pvr.engines.cpm import run_cpm
from pvr.engines.productivity import added_duration
from pvr.engines.quantities import QuantityLine, quantify_change
from pvr.models import ClaimedLine, ProjectData, RunContext

RATE_SOURCE = "BOQ rate, clause 13.3"


class CostLine(BaseModel):
    code: str
    description: str
    unit: str
    delta: float
    rate_aed: float
    amount_aed: float
    rate_source: str


class UnpricedItem(BaseModel):
    """A review item: priced at 0 and flagged, never guessed."""

    code: str
    description: str
    reason: str
    needs_new_rate: bool
    amount_aed: float = 0.0


class CostResult(BaseModel):
    change_type: str
    lines: list[CostLine]
    rate_source: str
    direct_cost_aed: float
    unpriced_items: list[UnpricedItem]

    @property
    def new_rate_items(self) -> list[UnpricedItem]:
        """Items that need a new rate agreed (clause 13.3)."""
        return [i for i in self.unpriced_items if i.needs_new_rate]


def price_change(ctx: RunContext, data: ProjectData) -> CostResult:
    """Cost per changed line = delta x BOQ rate. Review items are listed at 0, never priced."""
    q = quantify_change(ctx, data)
    lines = []
    for line in q.changed_lines():
        rate = data.boq_item(line.code).rate_aed
        lines.append(CostLine(
            code=line.code, description=line.description, unit=line.unit, delta=line.delta,
            rate_aed=rate, amount_aed=r2(line.delta * rate), rate_source=RATE_SOURCE,
        ))
    return CostResult(
        change_type=ctx.change_type,
        lines=lines,
        rate_source=RATE_SOURCE,
        direct_cost_aed=r2(sum(line.amount_aed for line in lines)),
        unpriced_items=[
            UnpricedItem(code=r.code, description=r.description, reason=r.reason, needs_new_rate=r.needs_new_rate)
            for r in q.requires_review
        ],
    )


# --- contractor claim comparison ------------------------------------------------


class ClaimLineComparison(BaseModel):
    claimed_description: str
    matched_code: str
    boq_description: str
    unit: str
    claimed_quantity: float
    assessed_quantity: float
    quantity_difference: float
    claimed_rate_aed: float
    boq_rate_aed: float
    rate_difference_aed: float
    claimed_amount_aed: float
    assessed_amount_aed: float
    amount_difference_aed: float
    clause: str


class ClaimAdjustment(BaseModel):
    item: str
    claimed: float
    assessed: float
    difference: float
    unit: str
    clause: str
    reason: str


class ClaimComparison(BaseModel):
    pvr_ref: str
    instruction_ref: str
    lines: list[ClaimLineComparison]
    claimed_subtotal_aed: float
    claimed_preliminaries_percent: float
    claimed_preliminaries_aed: float
    allowed_preliminaries_aed: float
    claimed_total_aed: float
    stated_total_matches_lines: bool
    assessed_direct_cost_aed: float
    difference_direct_aed: float
    claimed_extension_days: int
    assessed_extension_days_without_acceleration: int
    time_related_cost_per_day_aed: float
    time_related_cost_if_extension_granted_aed: float
    notice: NoticeCheck
    adjustments: list[ClaimAdjustment]


def _match_line(claimed: ClaimedLine, candidates: list[QuantityLine], data: ProjectData) -> QuantityLine:
    """Match a claimed line to the assessed line with the same unit and the best text match."""
    same_unit = [c for c in candidates if c.unit == claimed.unit]
    if not same_unit:
        raise EngineError(f"No assessed line with unit {claimed.unit} for claimed line '{claimed.description}'")
    scores = bm25_scores([f"{c.description} {data.boq_item(c.code).bill_name}" for c in same_unit],
                         claimed.description)
    best = max(range(len(same_unit)), key=lambda i: scores[i])
    return same_unit[best]


def no_acceleration_delay(ctx: RunContext, data: ProjectData) -> int:
    """Delay in working days with the change's new durations and no extra crews."""
    cpm = run_cpm(data, added_duration(ctx, data).new_durations())
    return max(0, cpm.completion_working_day - data.project.contract_completion_working_day)


def compare_contractor_claim(ctx: RunContext, data: ProjectData) -> ClaimComparison:
    """Line-by-line check of the contractor's PVR against the assessment. Contractor PVR mode only."""
    if not contractor_claim_applies(ctx):
        raise EngineError("There is no contractor claim to compare in internal what-if mode")
    pvr = data.documents.contractor_pvr
    vi = data.documents.variation_instruction
    refs = data.commercial.contract_clause_refs
    q = quantify_change(ctx, data)
    cost = price_change(ctx, data)
    candidates = q.changed_lines()

    lines: list[ClaimLineComparison] = []
    used: set[str] = set()
    for claimed in pvr.claimed_lines:
        match = _match_line(claimed, [c for c in candidates if c.code not in used], data)
        used.add(match.code)
        rate = data.boq_item(match.code).rate_aed
        claimed_amount = r2(claimed.quantity * claimed.rate_aed)
        assessed_amount = r2(match.delta * rate)
        lines.append(ClaimLineComparison(
            claimed_description=claimed.description, matched_code=match.code, boq_description=match.description,
            unit=claimed.unit, claimed_quantity=claimed.quantity, assessed_quantity=match.delta,
            quantity_difference=r2(claimed.quantity - match.delta),
            claimed_rate_aed=claimed.rate_aed, boq_rate_aed=rate, rate_difference_aed=r2(claimed.rate_aed - rate),
            claimed_amount_aed=claimed_amount, assessed_amount_aed=assessed_amount,
            amount_difference_aed=r2(claimed_amount - assessed_amount), clause=refs["valuation"],
        ))

    subtotal = r2(sum(line.claimed_amount_aed for line in lines))
    prelims = r2(subtotal * pvr.claimed_preliminaries_percent / 100)
    total = r2(subtotal + prelims)
    assessed_days = no_acceleration_delay(ctx, data)
    per_day = data.commercial.time_related_cost_per_working_day_aed

    adjustments = [
        ClaimAdjustment(
            item=f"{line.matched_code} rate", claimed=line.claimed_rate_aed, assessed=line.boq_rate_aed,
            difference=line.rate_difference_aed, unit="AED per " + line.unit, clause=refs["valuation"],
            reason="Variations are valued at BOQ rates for work of similar character.",
        )
        for line in lines if line.rate_difference_aed != 0
    ]
    adjustments += [
        ClaimAdjustment(
            item=f"{line.matched_code} quantity", claimed=line.claimed_quantity, assessed=line.assessed_quantity,
            difference=line.quantity_difference, unit=line.unit, clause=refs["valuation"],
            reason="Quantities are measured from the change.",
        )
        for line in lines if line.quantity_difference != 0
    ]
    adjustments.append(ClaimAdjustment(
        item="Preliminaries percentage", claimed=prelims, assessed=0.0, difference=prelims, unit="AED",
        clause=refs["preliminaries"],
        reason="BOQ rates include preliminaries; no percentage addition is allowed.",
    ))
    adjustments.append(ClaimAdjustment(
        item="Extension of time", claimed=pvr.claimed_extension_working_days, assessed=assessed_days,
        difference=pvr.claimed_extension_working_days - assessed_days, unit="working days",
        clause=refs["extension_of_time"],
        reason="Assessed on the critical path, taking account of float, without acceleration.",
    ))

    return ClaimComparison(
        pvr_ref=pvr.ref,
        instruction_ref=vi.ref,
        lines=lines,
        claimed_subtotal_aed=subtotal,
        claimed_preliminaries_percent=pvr.claimed_preliminaries_percent,
        claimed_preliminaries_aed=prelims,
        allowed_preliminaries_aed=0.0,
        claimed_total_aed=total,
        stated_total_matches_lines=abs(total - pvr.claimed_total_aed) < 0.01,
        assessed_direct_cost_aed=cost.direct_cost_aed,
        difference_direct_aed=r2(total - cost.direct_cost_aed),
        claimed_extension_days=pvr.claimed_extension_working_days,
        assessed_extension_days_without_acceleration=assessed_days,
        time_related_cost_per_day_aed=per_day,
        time_related_cost_if_extension_granted_aed=r2(per_day * assessed_days),
        notice=check_notice(vi.date, pvr.date, clause=refs["notice"]),
        adjustments=adjustments,
    )
