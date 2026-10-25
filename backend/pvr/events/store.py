"""Run store: `runs/<run_id>/events.jsonl`, one JSON event per line; recorded fixtures; replay timing.

A stored trace is found by its id: a run folder under `runs/`, or a recorded demo run
`fixtures/<name>.jsonl` (for example `demo_run_wall_height`). A fixture may keep the files its approved
actions wrote in `fixtures/<name>_outputs/`, so replays work offline.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from pvr.config import FIXTURES_DIR, RUNS_DIR
from pvr.models import Event

FIXTURE_PREFIX = "demo_run_"
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}")


def run_dir(run_id: str, runs_dir: Path = RUNS_DIR) -> Path:
    return runs_dir / run_id


class JsonlSink:
    """Appends each event to the run's events.jsonl and flushes, so the trace survives a crash."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._file = path.open("a", encoding="utf-8")

    def __call__(self, event: Event) -> None:
        if self._file.closed:
            return
        self._file.write(event.model_dump_json() + "\n")
        self._file.flush()

    def close(self) -> None:
        self._file.close()


def read_events(path: Path) -> list[Event]:
    """Read a stored trace."""
    with path.open(encoding="utf-8") as f:
        return [Event.model_validate(json.loads(line)) for line in f if line.strip()]


def is_safe_id(trace_id: str) -> bool:
    """True for ids that cannot leave their folder (letters, digits, `_`, `.`, `-`; no `..`)."""
    return bool(SAFE_ID.fullmatch(trace_id)) and ".." not in trace_id


def fixture_name(change_type: str) -> str:
    return f"{FIXTURE_PREFIX}{change_type}"


def find_trace(trace_id: str, runs_dir: Path = RUNS_DIR, fixtures_dir: Path = FIXTURES_DIR) -> Path | None:
    """The stored trace for a run id or a fixture name, or None."""
    if not is_safe_id(trace_id):
        return None
    for path in (runs_dir / trace_id / "events.jsonl", fixtures_dir / f"{trace_id}.jsonl"):
        if path.is_file():
            return path
    return None


def _first_event(path: Path) -> Event | None:
    with path.open(encoding="utf-8") as f:
        line = f.readline()
    return Event.model_validate(json.loads(line)) if line.strip() else None


def find_outputs_dir(trace_id: str, runs_dir: Path = RUNS_DIR, fixtures_dir: Path = FIXTURES_DIR) -> Path | None:
    """Where the approved actions of a run wrote their files: `runs/<id>/outputs/`, or for a fixture
    `fixtures/<name>_outputs/`. A fixture is also found by its original run id, so a replay can fetch
    outputs with the run id it sees in the events."""
    if not is_safe_id(trace_id):
        return None
    candidates = [runs_dir / trace_id / "outputs", fixtures_dir / f"{trace_id}_outputs"]
    if fixtures_dir.is_dir():
        for path in sorted(fixtures_dir.glob("*.jsonl")):
            first = _first_event(path)
            if first is not None and first.run_id == trace_id:
                candidates.append(fixtures_dir / f"{path.stem}_outputs")
    return next((c for c in candidates if c.is_dir()), None)


def list_traces(runs_dir: Path = RUNS_DIR, fixtures_dir: Path = FIXTURES_DIR) -> list[tuple[str, str, Path]]:
    """All stored traces as (id, source, path): fixtures first by name, then runs newest first."""
    fixtures = sorted(fixtures_dir.glob("*.jsonl")) if fixtures_dir.is_dir() else []
    runs = sorted((p for p in runs_dir.glob("*/events.jsonl")), reverse=True) if runs_dir.is_dir() else []
    return [(p.stem, "fixture", p) for p in fixtures] + [(p.parent.name, "run", p) for p in runs]


def save_fixture(run_id: str, runs_dir: Path = RUNS_DIR, fixtures_dir: Path = FIXTURES_DIR) -> Path:
    """Copy a completed, approved run to `fixtures/demo_run_<change_type>.jsonl` (and its outputs to
    `fixtures/demo_run_<change_type>_outputs/`). Replaces an earlier fixture for that change type."""
    path = runs_dir / run_id / "events.jsonl"
    if not is_safe_id(run_id) or not path.is_file():
        raise FileNotFoundError(f"No stored run {run_id}")
    events = read_events(path)
    started = next((e for e in events if e.type == "run.started"), None)
    if started is None or started.payload.get("kind") != "full":
        raise ValueError(f"Run {run_id} is not a full multi-agent run")
    if not any(e.type == "run.completed" and e.payload.get("status") == "approved" for e in events):
        raise ValueError(f"Run {run_id} did not complete with an approval")
    name = fixture_name(started.payload["context"]["change_type"])
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    target = fixtures_dir / f"{name}.jsonl"
    shutil.copyfile(path, target)
    outputs_target = fixtures_dir / f"{name}_outputs"
    if outputs_target.exists():
        shutil.rmtree(outputs_target)
    outputs = path.parent / "outputs"
    if outputs.is_dir():
        shutil.copytree(outputs, outputs_target)
    return target


# --- replay timing ---------------------------------------------------------------------------------------


def parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def replay_delays(events: list[Event], speed: float = 1.0, max_gap_s: float = 3.0) -> list[float]:
    """Seconds to wait before sending each event: the original gap to the previous event divided by
    `speed`, with each gap first capped at `max_gap_s` (0 means no cap). The first event has no wait."""
    if speed <= 0:
        raise ValueError("speed must be greater than 0")
    delays: list[float] = []
    previous: datetime | None = None
    for event in events:
        ts = parse_ts(event.ts)
        gap = 0.0 if previous is None else max(0.0, (ts - previous).total_seconds())
        if max_gap_s > 0:
            gap = min(gap, max_gap_s)
        delays.append(gap / speed)
        previous = ts
    return delays
