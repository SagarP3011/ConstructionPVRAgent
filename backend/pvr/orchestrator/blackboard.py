"""Blackboard: shared run state written by stages and read by agents (SPEC 10.3)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

SECTIONS: tuple[str, ...] = (
    "change", "quantities", "cost", "schedule_impact", "contract_findings", "options", "buffer",
    "claim_comparison", "stances", "pending_actions", "decision", "executed_actions",
)


class BlackboardEntry(BaseModel):
    section: str
    written_by: str
    content: Any


class Blackboard:
    """One entry per section; a later write replaces the earlier one."""

    def __init__(self) -> None:
        self._entries: dict[str, BlackboardEntry] = {}

    def write(self, section: str, content: Any, written_by: str) -> BlackboardEntry:
        if section not in SECTIONS:
            raise KeyError(f"Unknown blackboard section: {section}")
        entry = BlackboardEntry(section=section, written_by=written_by, content=content)
        self._entries[section] = entry
        return entry

    def read(self, section: str) -> BlackboardEntry | None:
        if section not in SECTIONS:
            raise KeyError(f"Unknown blackboard section: {section}")
        return self._entries.get(section)

    def filled(self) -> list[str]:
        """Sections with content, in SECTIONS order."""
        return [s for s in SECTIONS if s in self._entries]
