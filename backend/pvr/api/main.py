"""FastAPI application: REST routes and Server-Sent Events (SPEC 11).

Every SSE message carries one event as JSON (`id:` is the event id, `data:` the event). When a stream
has nothing more to send it emits a named `end` event, so clients can close instead of reconnecting.
Clients resume after a dropped connection with the `Last-Event-ID` header or the `after` query
parameter (an event id).
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from pvr import __version__
from pvr.api.runs import RunManager, RunStateError
from pvr.config import DATA_DIR, GOLDEN_PATH, load_settings
from pvr.data_loader import DATA_FILES, read_json
from pvr.engines.change import list_change_types, make_context
from pvr.engines.common import EngineError
from pvr.events.bus import EventBus
from pvr.events.snapshot import RunSnapshot, is_terminal
from pvr.events.store import find_outputs_dir, find_trace, is_safe_id, read_events, replay_delays
from pvr.llm.client import LLMError
from pvr.models import Event, Mode, Overrides
from pvr.orchestrator.approvals import ApprovalError

PING_SECONDS = 15.0
MIN_SLEEP_SECONDS = 0.01  # replay sends events due sooner than this without sleeping


class HealthResponse(BaseModel):
    """Response body of `GET /api/health`."""

    status: str
    version: str
    data_dir_found: bool
    golden_found: bool
    live_runs_available: bool  # an OpenAI key is configured; replays work without one


class StartRunRequest(BaseModel):
    change_type: str
    parameters: dict[str, float] = Field(default_factory=dict)  # missing parameters take their defaults
    mode: Mode | None = None  # default: the first mode of the change type
    overrides: Overrides | None = None


class StartRunResponse(BaseModel):
    run_id: str
    events_url: str
    snapshot_url: str


class ApproveRequest(BaseModel):
    option_id: str
    action_ids: list[str] = Field(default_factory=list)
    approver_name: str
    approver_role: str


class RejectRequest(BaseModel):
    approver_name: str
    approver_role: str
    reason: str


# --- SSE helpers -----------------------------------------------------------------------------------------


def sse_event(event: Event) -> str:
    return f"id: {event.event_id}\ndata: {event.model_dump_json()}\n\n"


def sse_end(reason: str) -> str:
    return f"event: end\ndata: {json.dumps({'reason': reason})}\n\n"


def events_after(events: list[Event], after: str | None) -> list[Event]:
    """Events after the one with id `after` (all events when `after` is empty or unknown)."""
    if after:
        for i, event in enumerate(events):
            if event.event_id == after:
                return events[i + 1:]
    return events


def sse_response(body: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(body, media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


async def stream_live(bus: EventBus, after: str | None) -> AsyncIterator[str]:
    """History first, then each new event as the run emits it, until the run ends."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[Event] = asyncio.Queue()

    def sink(event: Event) -> None:
        try:
            loop.call_soon_threadsafe(queue.put_nowait, event)
        except RuntimeError:  # the client's event loop is gone; the finally below removes this sink
            pass

    history = bus.subscribe(sink)
    try:
        for event in events_after(history, after):
            yield sse_event(event)
            if is_terminal(event):
                yield sse_end(event.type)
                return
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=PING_SECONDS)
            except asyncio.TimeoutError:
                yield ": ping\n\n"
                continue
            yield sse_event(event)
            if is_terminal(event):
                yield sse_end(event.type)
                return
    finally:
        bus.remove_sink(sink)


async def stream_stored(events: list[Event], delays: list[float] | None = None) -> AsyncIterator[str]:
    """A stored trace: at once, or with a wait before each event (replay). Waits are scheduled against
    the clock, so bursts of events in the same millisecond do not add up timer overhead."""
    loop = asyncio.get_running_loop()
    start = loop.time()
    due = 0.0
    for i, event in enumerate(events):
        if delays:
            due += delays[i]
            wait = start + due - loop.time()
            if wait > MIN_SLEEP_SECONDS:
                await asyncio.sleep(wait)
        yield sse_event(event)
    yield sse_end("run.completed" if events and events[-1].type == "run.completed" else "end_of_trace")


# --- application -------------------------------------------------------------------------------------------


def create_app(manager: RunManager | None = None) -> FastAPI:
    """Build the app. Tests pass a manager with a fake LLM and temporary folders."""
    app = FastAPI(title="PVR Agent Room", version=__version__)
    runs = manager or RunManager(load_settings())
    app.state.runs = runs
    if manager is None:
        # Read the stored traces once in the background, so the first run listing is quick.
        threading.Thread(target=runs.list_runs, name="warm-run-store", daemon=True).start()

    # The Vite dev server proxies /api, but allow direct calls from it too.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        """Health check. Also reports whether the repository data folders are reachable."""
        return HealthResponse(
            status="ok",
            version=__version__,
            data_dir_found=DATA_DIR.is_dir(),
            golden_found=GOLDEN_PATH.is_file(),
            live_runs_available=runs.settings.has_api_key,
        )

    @app.get("/api/change-types")
    def change_types() -> list[dict[str, Any]]:
        """Change types with parameters, defaults, ranges and modes."""
        return [ct.model_dump(mode="json") for ct in list_change_types(runs.data)]

    @app.get("/api/data/{name}")
    def data_file(name: str) -> Any:
        """One data file for the evidence panel."""
        if name not in DATA_FILES:
            raise HTTPException(404, f"Unknown data file {name}. Known: {', '.join(DATA_FILES)}")
        return read_json(name)

    @app.post("/api/runs", response_model=StartRunResponse, status_code=201)
    def start(body: StartRunRequest) -> StartRunResponse:
        """Start a live run. It runs stages 1 to 5, then waits for approval."""
        try:
            mode = body.mode or runs.data.change_type(body.change_type).modes[0]
            ctx = make_context(runs.data, body.change_type, body.parameters, mode=mode, overrides=body.overrides)
        except KeyError as exc:
            raise HTTPException(422, str(exc.args[0])) from None
        except EngineError as exc:
            raise HTTPException(422, str(exc)) from None
        try:
            live = runs.start(ctx)
        except LLMError as exc:
            raise HTTPException(503, f"Live runs are unavailable: {exc}. Replays still work.") from None
        rid = live.run_id
        return StartRunResponse(run_id=rid, events_url=f"/api/runs/{rid}/events", snapshot_url=f"/api/runs/{rid}")

    @app.get("/api/runs")
    def list_runs() -> list[dict[str, Any]]:
        """Recorded fixtures and stored runs."""
        return runs.list_runs()

    @app.get("/api/runs/{run_id}", response_model=RunSnapshot)
    def snapshot(run_id: str) -> RunSnapshot:
        """Current state of a live run, a stored run or a fixture."""
        snap = runs.snapshot(run_id)
        if snap is None:
            raise HTTPException(404, f"No run {run_id}")
        return snap

    @app.get("/api/runs/{run_id}/events")
    def events(run_id: str, after: str | None = None,
               last_event_id: str | None = Header(default=None)) -> StreamingResponse:
        """SSE stream of a run's events: live as they happen, or a stored run's events at once."""
        start_after = last_event_id or after
        live = runs.get(run_id)
        if live is not None:
            return sse_response(stream_live(live.bus, start_after))
        path = find_trace(run_id, runs.runs_dir, runs.fixtures_dir)
        if path is None:
            raise HTTPException(404, f"No run {run_id}")
        return sse_response(stream_stored(events_after(read_events(path), start_after)))

    @app.post("/api/runs/{run_id}/approve")
    def approve(run_id: str, body: ApproveRequest) -> dict[str, Any]:
        """A named person approves one presented option and the actions to execute."""
        try:
            executed = runs.approve(run_id, body.option_id, body.action_ids, body.approver_name, body.approver_role)
        except RunStateError as exc:
            raise HTTPException(409, str(exc)) from None
        except ApprovalError as exc:
            raise HTTPException(400, str(exc)) from None
        return {"run_id": run_id, "status": "approved", "option_id": body.option_id,
                "executed_actions": [e.model_dump() for e in executed]}

    @app.post("/api/runs/{run_id}/reject")
    def reject(run_id: str, body: RejectRequest) -> dict[str, Any]:
        """A named person rejects the run with a reason. Nothing is executed."""
        try:
            decision = runs.reject(run_id, body.approver_name, body.approver_role, body.reason)
        except RunStateError as exc:
            raise HTTPException(409, str(exc)) from None
        except ApprovalError as exc:
            raise HTTPException(400, str(exc)) from None
        return {"run_id": run_id, "status": "rejected", "decision": decision.model_dump()}

    @app.get("/api/runs/{run_id}/outputs/{file_name}")
    def output_file(run_id: str, file_name: str) -> FileResponse:
        """Download a file written by an approved action."""
        folder = find_outputs_dir(run_id, runs.runs_dir, runs.fixtures_dir)
        if folder is None or not is_safe_id(file_name) or not (folder / file_name).is_file():
            raise HTTPException(404, f"No output {file_name} for run {run_id}")
        return FileResponse(folder / file_name)

    @app.get("/api/replay/{trace_id}")
    def replay(
        trace_id: str,
        speed: float = Query(1.0, gt=0, le=50, description="Playback speed; 2 plays twice as fast"),
        max_gap: float = Query(3.0, ge=0, le=600, description="Longest pause in seconds before speed; 0 = none"),
        after: str | None = None,
        last_event_id: str | None = Header(default=None),
    ) -> StreamingResponse:
        """SSE replay of a stored run or fixture with its original timing. Needs no API key."""
        path = find_trace(trace_id, runs.runs_dir, runs.fixtures_dir)
        if path is None:
            raise HTTPException(404, f"No stored run or fixture {trace_id}")
        stored = events_after(read_events(path), last_event_id or after)
        return sse_response(stream_stored(stored, replay_delays(stored, speed, max_gap)))

    return app


app = create_app()
