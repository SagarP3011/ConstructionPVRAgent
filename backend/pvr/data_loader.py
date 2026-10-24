"""Load and validate the data files from `data/` at the repository root."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pvr.config import DATA_DIR
from pvr.models import (
    BoqItem,
    Commercial,
    Contract,
    Documents,
    Productivity,
    Project,
    ProjectData,
    Scenario,
    Schedule,
)

DATA_FILES: tuple[str, ...] = (
    "project", "boq", "schedule", "productivity", "commercial", "contract", "documents", "scenario",
)


def read_json(name: str, data_dir: Path = DATA_DIR) -> Any:
    """Read one data file (`name` without `.json`) as raw JSON."""
    if name not in DATA_FILES:
        raise KeyError(f"Unknown data file: {name}")
    with (data_dir / f"{name}.json").open(encoding="utf-8") as f:
        return json.load(f)


def load_data(data_dir: Path = DATA_DIR) -> ProjectData:
    """Load every data file and validate it against the Pydantic models."""
    return ProjectData(
        project=Project.model_validate(read_json("project", data_dir)),
        boq=[BoqItem.model_validate(row) for row in read_json("boq", data_dir)],
        schedule=Schedule.model_validate(read_json("schedule", data_dir)),
        productivity=Productivity.model_validate(read_json("productivity", data_dir)),
        commercial=Commercial.model_validate(read_json("commercial", data_dir)),
        contract=Contract.model_validate(read_json("contract", data_dir)),
        documents=Documents.model_validate(read_json("documents", data_dir)),
        scenario=Scenario.model_validate(read_json("scenario", data_dir)),
    )


@lru_cache(maxsize=1)
def get_data() -> ProjectData:
    """The repository data, loaded once. The data files are read-only inputs."""
    return load_data()
