"""Blackboard: shared run state written by stages and read by agents (SPEC 10.3)."""

from __future__ import annotations

import threading
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
    """One entry per section. `write` replaces a section; `merge` adds keys to a dict section."""

    def __init__(self) -> None:
        self._entries: dict[str, BlackboardEntry] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _check(section: str) -> None:
        if section not in SECTIONS:
            raise KeyError(f"Unknown blackboard section: {section}")

    def write(self, section: str, content: Any, written_by: str) -> BlackboardEntry:
        self._check(section)
        with self._lock:
            entry = BlackboardEntry(section=section, written_by=written_by, content=content)
            self._entries[section] = entry
            return entry

    def merge(self, section: str, key: str, value: Any, written_by: str) -> BlackboardEntry:
        """Set `content[key] = value` in a dict section, keeping the other keys."""
        self._check(section)
        with self._lock:
            old = self._entries.get(section)
            content = dict(old.content) if old and isinstance(old.content, dict) else {}
            content[key] = value
            authors = {a for a in (old.written_by.split(", ") if old else []) if a} | {written_by}
            entry = BlackboardEntry(section=section, written_by=", ".join(sorted(authors)), content=content)
            self._entries[section] = entry
            return entry

    def read(self, section: str) -> BlackboardEntry | None:
        self._check(section)
        with self._lock:
            return self._entries.get(section)

    def filled(self) -> list[str]:
        """Sections with content, in SECTIONS order."""
        with self._lock:
            return [s for s in SECTIONS if s in self._entries]
