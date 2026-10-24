"""Buffer engine: check an option against the time buffer and the cost contingency (SPEC 7.9)."""

from __future__ import annotations

from pydantic import BaseModel

from pvr.engines.common import r2
from pvr.engines.options import contingency_aed, evaluate_option, parse_option_id, time_buffer_days
from pvr.models import ProjectData, RunContext


class BufferCheck(BaseModel):
    option_id: str
    delay_working_days: int
    total_cost_aed: float
    time_buffer_days: int
    contingency_aed: float
    time_buffer_remaining_days: int
    contingency_remaining_aed: float
    within_time_buffer: bool
    within_contingency: bool
    budget_uplift_needed_aed: float
    exceeds_employer_commitment: bool


def check_buffer(ctx: RunContext, data: ProjectData, option_id: str) -> BufferCheck:
    """Time buffer and contingency left after an option, and the budget uplift it needs (0 if none)."""
    option = evaluate_option(ctx, data, parse_option_id(option_id, data))
    buffer_left = option.time_buffer_remaining_days
    money_left = option.contingency_remaining_aed
    return BufferCheck(
        option_id=option.option_id,
        delay_working_days=option.delay_working_days,
        total_cost_aed=option.total_cost_aed,
        time_buffer_days=time_buffer_days(ctx, data),
        contingency_aed=contingency_aed(ctx, data),
        time_buffer_remaining_days=buffer_left,
        contingency_remaining_aed=money_left,
        within_time_buffer=buffer_left >= 0,
        within_contingency=money_left >= 0,
        budget_uplift_needed_aed=r2(max(0.0, -money_left)),
        exceeds_employer_commitment=buffer_left < 0,
    )
