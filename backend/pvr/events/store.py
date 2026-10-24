"""Run store: `runs/<run_id>/events.jsonl`, one JSON event per line."""

from __future__ import annotations

import json
from pathlib import Path

from pvr.config import RUNS_DIR
from pvr.models import Event


def run_dir(run_id: str, runs_dir: Path = RUNS_DIR) -> Path:
    return runs_dir / run_id


class JsonlSink:
    """Appends each event to the run's events.jsonl and flushes, so the trace survives a crash."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._file = path.open("a", encoding="utf-8")

    def __call__(self, event: Event) -> None:
        self._file.write(event.model_dump_json() + "\n")
        self._file.flush()

    def close(self) -> None:
        self._file.close()


def read_events(path: Path) -> list[Event]:
    """Read a stored trace."""
    with path.open(encoding="utf-8") as f:
        return [Event.model_validate(json.loads(line)) for line in f if line.strip()]
