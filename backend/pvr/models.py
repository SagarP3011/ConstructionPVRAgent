"""Pydantic models for the data files and the run context.

Data models mirror the JSON files in `data/` exactly (unknown fields are rejected,
so a change to a data file is noticed). Engine result models live next to their
engines in `pvr/engines/`.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DataModel(BaseModel):
    """Base for data-file models: strict about unknown fields, immutable."""

    model_config = ConfigDict(extra="forbid", frozen=True)


# --- project.json -------------------------------------------------------------


class Calendar(DataModel):
    start_date: date
    working_days: list[str]
    non_working_days: list[str]
    holidays: list[date]


class Project(DataModel):
    project_id: str
    name: str
    note: str
    employer: str
    contractor: str
    contract_ref: str
    contract_type: str
    currency: str
    calendar: Calendar
    data_date_working_day: int
    data_date: date
    contract_completion_working_day: int
    contract_completion_date: date
    employer_commitment_working_day: int
    employer_commitment_date: date
    time_buffer_working_days: int
    cost_contingency_remaining_aed: float


# --- boq.json -----------------------------------------------------------------


class BoqItem(DataModel):
    bill: str
    bill_name: str
    code: str
    description: str
    unit: str
    quantity: float
    rate_aed: float
    amount_aed: float
    lump_sum: bool


# --- schedule.json ------------------------------------------------------------


class Relationship(DataModel):
    id: str
    type: Literal["FS", "SS"]
    lag: int


class Activity(DataModel):
    id: str
    name: str
    wbs: str
    zone: str
    discipline: str
    duration: int
    predecessors: list[Relationship]
    boq_codes: list[str]
    status: str


class Schedule(DataModel):
    units: str
    note: str
    activities: list[Activity]


# --- productivity.json --------------------------------------------------------


class ProductivityItem(DataModel):
    boq_code: str
    activity_id: str
    productivity: float
    unit: str


class Productivity(DataModel):
    units: str
    rule: str
    items: list[ProductivityItem]


# --- commercial.json ----------------------------------------------------------


class AdditionalCrew(DataModel):
    mobilisation_aed_per_crew_per_activity: float
    day_rate_aed: float
    max_additional_crews_per_activity: int
    rule: str
    eligible_activities_by_change_type: dict[str, list[str]]


class Commercial(DataModel):
    time_related_cost_per_working_day_aed: float
    additional_crew: AdditionalCrew
    contract_clause_refs: dict[str, str]


# --- contract.json ------------------------------------------------------------


class Clause(DataModel):
    clause: str
    title: str
    text: str


class Contract(DataModel):
    contract_ref: str
    clauses: list[Clause]


# --- documents.json -----------------------------------------------------------


class RoadGeometry(DataModel):
    drawing: str
    revision: str
    length_m: float
    formation_width_m: float
    excavation_depth_m: float
    layers: dict[str, str]
    note: str


class HardscapeGeometry(DataModel):
    drawing: str
    revision: str
    interlocking_paving_area_m2: float
    granite_paving_area_m2: float
    note: str


class ElementGeometry(DataModel):
    internal_road: RoadGeometry
    hardscape: HardscapeGeometry


class WallKeyData(DataModel):
    wall_height_m: float
    wall_length_m: float
    wall_thickness_m: float
    faces_finished: int
    stiffener_column_spacing_m: float
    stiffener_column_section_m: tuple[float, float]


class DrawingRevision(DataModel):
    drawing: str
    revision: str
    title: str
    status: str
    date: date
    key_data: WallKeyData
    revision_note: str | None = None


class VariationInstruction(DataModel):
    ref: str
    date: date
    issued_by: str
    text: str


class ClaimedLine(DataModel):
    description: str
    unit: str
    quantity: float
    rate_aed: float


class ContractorPvr(DataModel):
    ref: str
    date: date
    contractor: str
    subject: str
    text: str
    claimed_lines: list[ClaimedLine]
    claimed_preliminaries_percent: float
    claimed_total_aed: float
    claimed_extension_working_days: int


class Documents(DataModel):
    element_geometry: ElementGeometry
    drawing_register: list[DrawingRevision]
    variation_instruction: VariationInstruction
    contractor_pvr: ContractorPvr


# --- scenario.json ------------------------------------------------------------

Mode = Literal["contractor_pvr", "internal_what_if"]


class ParameterSpec(DataModel):
    name: str
    label: str
    default: float
    min: float
    max: float
    step: float


class ChangeType(DataModel):
    id: str
    title: str
    element: str
    parameters: list[ParameterSpec]
    fixed: dict[str, float] = Field(default_factory=dict)
    has_contractor_claim_at_default: bool
    default_instruction: str
    modes: list[Mode]


class Scenario(DataModel):
    change_types: list[ChangeType]
    note: str


# --- all data -------------------------------------------------------------------


class ProjectData(DataModel):
    """Every data file, loaded and validated."""

    project: Project
    boq: list[BoqItem]
    schedule: Schedule
    productivity: Productivity
    commercial: Commercial
    contract: Contract
    documents: Documents
    scenario: Scenario

    def boq_item(self, code: str) -> BoqItem:
        """Return the BOQ line with this code. Raises KeyError if unknown."""
        for item in self.boq:
            if item.code == code:
                return item
        raise KeyError(f"Unknown BOQ code: {code}")

    def change_type(self, change_type_id: str) -> ChangeType:
        """Return the change type with this id. Raises KeyError if unknown."""
        for ct in self.scenario.change_types:
            if ct.id == change_type_id:
                return ct
        raise KeyError(f"Unknown change type: {change_type_id}")


# --- run context ----------------------------------------------------------------


class Overrides(BaseModel):
    """Optional what-if overrides for the Employer's limits."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cost_contingency_remaining_aed: float | None = None
    time_buffer_working_days: int | None = None


class RunContext(BaseModel):
    """Fixed at run start and passed to every tool. Build it with `engines.change.make_context`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    change_type: str
    parameters: dict[str, float]
    mode: Mode = "internal_what_if"
    overrides: Overrides = Field(default_factory=Overrides)
