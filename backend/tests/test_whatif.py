"""What-if behaviour behind Checkpoint 6: a bigger change and a larger contingency change the decision."""

from __future__ import annotations

import json

import pytest

from pvr.cli import main
from pvr.config import GOLDEN_PATH
from pvr.data_loader import get_data
from pvr.engines import buffer, options
from pvr.engines.change import make_context
from pvr.models import Overrides

GOLDEN = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def golden_case(change_type: str, parameters: dict[str, float]) -> dict:
    return next(c for c in GOLDEN["cases"] if c["change_type"] == change_type and c["parameters"] == parameters)


def golden_option(case: dict, option_id: str) -> dict:
    return next(o for o in case["options_all"] if o["option_id"] == option_id)


def test_wall_at_3_m_breaks_the_buffer_without_crews_and_changes_the_options() -> None:
    data = get_data()
    ctx = make_context(data, "wall_height", {"new_height_m": 3.0})
    check = buffer.check_buffer(ctx, data, "OPT-NONE")
    assert check.exceeds_employer_commitment and check.time_buffer_remaining_days < 0
    default = golden_case("wall_height", {"new_height_m": 2.5})["pareto_option_ids"]
    assert options.search_options(ctx, data).pareto_option_ids != default


def test_contingency_of_75000_makes_holding_the_wall_date_fit_the_budget() -> None:
    data = get_data()
    base = make_context(data, "wall_height", mode="contractor_pvr")
    assert not buffer.check_buffer(base, data, "OPT-A320").within_contingency

    ctx = make_context(data, "wall_height", mode="contractor_pvr",
                       overrides=Overrides(cost_contingency_remaining_aed=75000))
    check = buffer.check_buffer(ctx, data, "OPT-A320")
    total = golden_option(golden_case("wall_height", {"new_height_m": 2.5}), "OPT-A320")["total_cost_aed"]
    assert check.within_contingency and check.budget_uplift_needed_aed == 0
    assert check.contingency_remaining_aed == pytest.approx(75000 - total)


def test_engines_cli_accepts_what_if_limits(capsys: pytest.CaptureFixture[str]) -> None:
    # A 5-day buffer is broken by the 8-day delay of accepting the delay (OPT-NONE) at the default wall.
    assert main(["engines", "--change", "wall_height", "--contingency", "75000", "--time-buffer", "5"]) == 0
    out = capsys.readouterr().out
    none_row = next(line for line in out.splitlines() if "OPT-NONE " in line and "none" in line)
    assert "breach" in none_row
    a320_row = next(line for line in out.splitlines() if line.strip().startswith(("* OPT-A320 ", "OPT-A320 ")))
    assert "uplift" not in a320_row
