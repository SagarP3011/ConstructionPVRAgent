"""The `engines` CLI prints the deterministic assessment of SPEC 2.4 for the three defaults."""

from __future__ import annotations

import pytest

from pvr.cli import main


def test_engines_report_defaults(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["engines"]) == 0
    out = capsys.readouterr().out
    wall, road, paving = out.split("\n\n== ")

    assert "Direct cost: AED 43,529" in wall
    assert "Added duration 14 wd in total; baseline float of the affected chain 6 wd; delay without acceleration 8 wd" in wall
    assert "presented in this order: OPT-A320, OPT-A340, OPT-NONE" in wall
    assert "-4,929 (uplift needed)" in wall
    assert "= AED 61,419.60; extension 21 wd" in wall
    assert "within 28 days (clause 20.1)" in wall

    assert "Direct cost: AED 100,440" in road
    assert "R-02-050: AED 0 (new rate needed)" in road
    assert "presented in this order: OPT-A120, OPT-NONE" in road

    assert "Direct cost: AED 36,800" in paving
    assert "presented in this order: OPT-NONE)" in paving
    assert "delay without acceleration 0 wd" in paving


def test_engines_single_change(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["engines", "--change", "wall_height", "--param", "new_height_m=3.0"]) == 0
    out = capsys.readouterr().out
    assert "Direct cost: AED 87,058" in out
    assert "(breach)" in out
    assert "Contractor claim check" not in out


def test_engines_rejects_invalid_parameter(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["engines", "--change", "paving_area", "--param", "added_area_m2=5000"]) == 2
    assert "must be between" in capsys.readouterr().err
