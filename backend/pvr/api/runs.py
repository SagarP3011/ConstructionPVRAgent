"""Live run registry for the API: starts runs in background threads, holds them while they wait for
approval, and answers snapshots for live and stored runs.

This is the API's one explicit registry of in-memory state. A run waiting for approval lives only
here: after a server restart its trace remains, but it can no longer be approved.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

from pvr.config import FIXTURES_DIR, RUNS_DIR, Settings
from pvr.data_loader import get_data
from pvr.events.bus import EventBus
from pvr.events.snapshot import RunSnapshot, run_snapshot
from pvr.events.store import JsonlSink, find_trace, list_traces, read_events
from pvr.llm.client import LLM, OpenAILLM
from pvr.models import ProjectData, RunContext
from pvr.orchestrator.actions import ExecutedAction
from pvr.orchestrator.approvals import Decision
from pvr.orchestrator.orchestrator import Orchestrator, RunAborted, start_run

LLMFactory = Callable[[Settings], LLM]


class RunStateError(RuntimeError):
    """The run is not in a state that allows this request (for example approving twice)."""


class LiveRun:
    """One run held in memory: its orchestrator, its trace file and a lock for approval requests."""

    def __init__(self, orchestrator: Orchestrator, sink: JsonlSink) -> None:
        self.orchestrator = orchestrator
        self.sink = sink
        self.lock = threading.Lock()
        self.thread: threading.Thread | None = None

    @property
    def run_id(self) -> str:
        return self.orchestrator.session.run_id

    @property
    def bus(self) -> EventBus:
        return self.orchestrator.session.bus

    def snapshot(self) -> RunSnapshot:
        snap = run_snapshot(self.bus.history(), self.run_id)
        snap.live = True
        return snap

    def close(self) -> None:
        self.sink.close()


class RunManager:
    def __init__(
        self,
        settings: Settings,
        runs_dir: Path = RUNS_DIR,
        fixtures_dir: Path = FIXTURES_DIR,
        llm_factory: LLMFactory = OpenAILLM,
        data: ProjectData | None = None,
    ) -> None:
        self.settings = settings
        self.runs_dir = runs_dir
        self.fixtures_dir = fixtures_dir
        self.llm_factory = llm_factory
        self.data = data or get_data()
        self._runs: dict[str, LiveRun] = {}
        # Snapshots of stored traces, keyed by (path, size, modified time): a finished trace never changes.
        self._snapshots: dict[tuple[str, int, int], RunSnapshot] = {}
        self._lock = threading.Lock()

    # --- starting and running -----------------------------------------------------------------------

    def start(self, ctx: RunContext) -> LiveRun:
        """Create the run and start stages 1 to 5 in a background thread. Raises LLMError without a key."""
        llm = self.llm_factory(self.settings)
        orchestrator, sink = start_run(ctx, self.data, self.settings, llm, runs_dir=self.runs_dir)
        live = LiveRun(orchestrator, sink)
        with self._lock:
            self._runs[live.run_id] = live
        live.thread = threading.Thread(target=self._run_stages, args=(live,), name=f"run-{live.run_id}",
                                       daemon=True)
        live.thread.start()
        return live

    def _run_stages(self, live: LiveRun) -> None:
        try:
            live.orchestrator.run_until_approval()
        except RunAborted:
            live.close()  # the orchestrator has emitted the fatal error
        except Exception as exc:  # noqa: BLE001 - any failure ends the run with a visible error event
            error = (str(exc) or type(exc).__name__)
            if self.settings.openai_api_key:
                error = error.replace(self.settings.openai_api_key, "***")
            live.bus.emit("run.error", {"error": error, "fatal": True, "stage": live.orchestrator.session.stage})
            live.close()

    # --- approval -----------------------------------------------------------------------------------

    def _awaiting(self, run_id: str) -> LiveRun:
        live = self.get(run_id)
        if live is None:
            raise RunStateError("This run is not held by the server, so it cannot be approved or rejected")
        if live.orchestrator.state != "awaiting_approval":
            raise RunStateError(f"This run is not waiting for approval (state: {live.orchestrator.state})")
        return live

    def approve(self, run_id: str, option_id: str, action_ids: list[str], approver_name: str,
                approver_role: str) -> list[ExecutedAction]:
        """Approve one presented option and execute the approved actions. Raises ApprovalError for an
        invalid approval and RunStateError when the run is not waiting for one."""
        live = self._awaiting(run_id)
        with live.lock:
            self._awaiting(run_id)  # re-check: another request may have decided meanwhile
            executed = live.orchestrator.approve(option_id, action_ids, approver_name, approver_role)
            live.close()
            return executed

    def reject(self, run_id: str, approver_name: str, approver_role: str, reason: str) -> Decision:
        live = self._awaiting(run_id)
        with live.lock:
            self._awaiting(run_id)
            decision = live.orchestrator.reject(approver_name, approver_role, reason)
            live.close()
            return decision

    # --- lookup ---------------------------------------------------------------------------------------

    def get(self, run_id: str) -> LiveRun | None:
        with self._lock:
            return self._runs.get(run_id)

    def snapshot(self, trace_id: str) -> RunSnapshot | None:
        """Snapshot of a live run, a stored run or a fixture; None if unknown."""
        live = self.get(trace_id)
        if live is not None:
            return live.snapshot()
        path = find_trace(trace_id, self.runs_dir, self.fixtures_dir)
        if path is None:
            return None
        stat = path.stat()
        key = (str(path), stat.st_size, stat.st_mtime_ns)
        with self._lock:
            cached = self._snapshots.get(key)
        if cached is None:
            cached = run_snapshot(read_events(path), trace_id)
            with self._lock:
                self._snapshots[key] = cached
        return cached.model_copy(deep=True)

    def list_runs(self) -> list[dict[str, object]]:
        """Fixtures and stored runs with a short summary each."""
        rows: list[dict[str, object]] = []
        for trace_id, source, _ in list_traces(self.runs_dir, self.fixtures_dir):
            snap = self.snapshot(trace_id)
            if snap is None:
                continue
            rows.append({
                "id": trace_id, "source": source, "run_id": snap.run_id, "kind": snap.kind, "state": snap.state,
                "live": snap.live, "change_type": snap.context.get("change_type"),
                "parameters": snap.context.get("parameters"), "mode": snap.context.get("mode"),
                "started_at": snap.started_at, "ended_at": snap.ended_at, "event_count": snap.event_count,
                "chosen_option": (snap.decision or {}).get("option_id"),
            })
        return rows
