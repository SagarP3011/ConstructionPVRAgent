"""Sequential ids per run (F-0001 facts, T-0001 tool calls, M-0001 messages, E-000001 events)."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone


class IdGen:
    """Counter per prefix. One instance per run, so ids are deterministic within a run."""

    def __init__(self) -> None:
        self._counters: dict[str, int] = {}

    def next(self, prefix: str, width: int = 4) -> str:
        n = self._counters.get(prefix, 0) + 1
        self._counters[prefix] = n
        return f"{prefix}-{n:0{width}d}"


def new_run_id() -> str:
    """Run id such as R-20261024-153012-a1b2 (UTC time plus a random suffix)."""
    return "R-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)


def now_iso() -> str:
    """Current UTC time, ISO 8601 with milliseconds."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")
