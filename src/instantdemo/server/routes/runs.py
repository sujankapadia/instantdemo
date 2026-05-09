"""Run orchestration: kick off a multi-phase pipeline from the GUI,
stream typed events back over SSE, and support cancellation.

The single FastAPI process owns one ClaudeSDKClient (the long-lived
Iteration 12 client), connecting it lazily on the first run and
disconnecting at app shutdown. Phases run sequentially against that
client; per-phase tool allowlists are enforced by the same
PhaseDispatcher the CLI uses.

v1 enforces a single-active-run constraint — concurrent POST /api/runs
returns 409 while a run is in flight. The PhaseDispatcher's
`current_phase` attribute is mutated across the run, and the SDK's
ClaudeSDKClient docs note that a single client instance can't be
used across different async runtime contexts. Both make concurrency
unsafe today; serialization is the simpler defense.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from instantdemo.agent_client import make_agent_client
from instantdemo.phases import (
    Context,
    PHASES,
    phase_name_from_number,
)
from instantdemo import state as state_mod


router = APIRouter(prefix="/api", tags=["runs"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class RunRequest(BaseModel):
    """Body of POST /api/runs.

    `phases` is the list of 1-based phase numbers to run, in order.
    Cold start is `[1, 2, 3, 4, 5]`; running a single phase is `[3]`;
    "from phase 3 onward" is `[3, 4, 5]`. The other fields are
    project-level inputs the CLI's `instantdemo generate` would
    otherwise read from flags.
    """

    phases: list[int]
    url: str
    describe: str | None = None
    tts: str = "kokoro"


class RunInfo(BaseModel):
    """Returned from POST /api/runs."""

    run_id: str
    phases: list[int]
    started_at: str


class RunStatus(BaseModel):
    """Returned from GET /api/runs/{run_id}."""

    run_id: str
    phases: list[int]
    status: Literal["running", "complete", "canceled", "error"]
    current_phase: int | None = None
    started_at: str
    ended_at: str | None = None
    total_cost_usd: float | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Run state (in-memory, single-active-run)
# ---------------------------------------------------------------------------


class _Run:
    """Runtime state for a single multi-phase run."""

    def __init__(self, run_id: str, phases: list[int]) -> None:
        self.run_id = run_id
        self.phases = list(phases)
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.task: asyncio.Task[None] | None = None
        self.status: Literal["running", "complete", "canceled", "error"] = "running"
        self.current_phase: int | None = None
        self.started_at = _now_iso()
        self.ended_at: str | None = None
        self.total_cost_usd: float = 0.0
        self.error: str | None = None
        # Sentinel pushed onto the queue when the run is done so
        # SSE consumers know to close the stream.
        self._done = asyncio.Event()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _project_dir() -> Path:
    """Same resolution rule as routes/project.py."""
    override = os.environ.get("INSTANTDEMO_PROJECT_DIR")
    return Path(override).resolve() if override else Path.cwd()


class RunManager:
    """Process-wide singleton owning the ClaudeSDKClient and the
    currently-active run. Lazily connects the client on the first
    /api/runs request and disconnects it at app shutdown."""

    def __init__(self) -> None:
        self._client: Any = None
        self._dispatcher: Any = None
        self._client_cwd: str | None = None
        self.active: _Run | None = None
        self._lock = asyncio.Lock()

    async def _ensure_client(self, cwd: str) -> None:
        """Create-and-connect the ClaudeSDKClient on first use, or
        reconnect with a different cwd if the project changed."""
        if self._client is not None and self._client_cwd == cwd:
            return
        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception:
                pass
        self._client, self._dispatcher = make_agent_client(cwd=cwd)
        self._client_cwd = cwd
        await self._client.connect()

    async def shutdown(self) -> None:
        """Called from FastAPI lifespan on app exit."""
        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception:
                pass
            self._client = None
            self._dispatcher = None
            self._client_cwd = None

    async def start_run(self, request: RunRequest) -> _Run:
        """Validate inputs, lazily connect the client, reset state for
        the requested phases, then spawn the background pipeline task.

        The phase reset happens synchronously here (not in _execute) so
        that the response we return to the client reflects the new
        pending state — eliminates a race where the client could
        refetch /api/project and see stale phase data from a previous
        run before the background task gets to clear it."""
        for phase_num in request.phases:
            if not 1 <= phase_num <= len(PHASES):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"phase {phase_num} out of range (1..{len(PHASES)})",
                )

        async with self._lock:
            if self.active is not None and self.active.status == "running":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="another run is already in progress",
                )
            project = _project_dir()
            await self._ensure_client(str(project))

            # Reset state for phases in this run. Phases not in the
            # request keep their existing entries (so a targeted re-run
            # of phase 3 doesn't wipe phases 1, 2, 4, 5).
            state_dir = project / ".instantdemo"
            state_dir.mkdir(parents=True, exist_ok=True)
            s = state_mod.load(state_dir)
            phases_dict = s.setdefault("phases", {})
            for phase_num in request.phases:
                phases_dict[str(phase_num)] = {"status": "pending"}
            state_mod.update_inputs(s, url=request.url, describe=request.describe)
            state_mod.save(state_dir, s)

            run = _Run(run_id=str(uuid.uuid4()), phases=request.phases)
            self.active = run
            run.task = asyncio.create_task(
                self._execute(run, request, project),
                name=f"run-{run.run_id}",
            )
            return run

    async def cancel(self, run_id: str) -> None:
        """Cancel the active run if its id matches."""
        run = self.active
        if run is None or run.run_id != run_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="no such run, or run already finished",
            )
        if run.status != "running":
            return
        # Tell the SDK first — interrupt() is near-instant per the spike.
        if self._client is not None:
            try:
                await self._client.interrupt()
            except Exception:
                pass
        # Then cancel the asyncio task. The execution coroutine catches
        # CancelledError, marks status, and signals the queue.
        if run.task is not None and not run.task.done():
            run.task.cancel()

    def get_status(self, run_id: str) -> RunStatus:
        run = self.active
        if run is None or run.run_id != run_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="no such run",
            )
        return RunStatus(
            run_id=run.run_id,
            phases=run.phases,
            status=run.status,
            current_phase=run.current_phase,
            started_at=run.started_at,
            ended_at=run.ended_at,
            total_cost_usd=run.total_cost_usd if run.status != "running" else None,
            error=run.error,
        )

    async def stream_events(self, run_id: str):
        """Yield SSE events from the run's queue until the run ends."""
        run = self.active
        if run is None or run.run_id != run_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="no such run",
            )
        while True:
            # Wait for either an event or the run to finish.
            try:
                event = await asyncio.wait_for(run.queue.get(), timeout=15.0)
                yield {"event": "message", "data": _json_dumps(event)}
                if event.get("type") in ("run_complete", "run_canceled", "run_error"):
                    break
            except asyncio.TimeoutError:
                # Heartbeat — keeps the connection open and lets the
                # client detect a dropped connection.
                yield {"event": "heartbeat", "data": ""}
                if run.status != "running":
                    break

    # -- internals ---------------------------------------------------------

    async def _execute(
        self, run: _Run, request: RunRequest, project: Path
    ) -> None:
        """Background task that runs the requested phases sequentially
        and pushes events onto run.queue."""
        state_dir = project / ".instantdemo"
        output = project / "demo.mp4"
        context = Context(
            url=request.url,
            source=project,
            describe=request.describe,
            state_dir=state_dir,
            output=output,
            tts=request.tts,
            no_edit=True,  # GUI checkpoints are out-of-band
            client=self._client,
            dispatcher=self._dispatcher,
            event_emitter=lambda evt: run.queue.put_nowait(evt),
        )
        # State.json was already prepared in start_run (phases reset to
        # pending, run-level inputs recorded). Just proceed.

        try:
            for phase_num in request.phases:
                run.current_phase = phase_num
                phase_name = phase_name_from_number(phase_num)
                run.queue.put_nowait(
                    {
                        "type": "phase_started",
                        "phase": phase_num,
                        "phase_name": phase_name,
                        "ts": _now_iso(),
                    }
                )
                try:
                    await _run_one_phase(phase_num, context)
                except Exception as exc:
                    run.queue.put_nowait(
                        {
                            "type": "phase_error",
                            "phase": phase_num,
                            "error": str(exc),
                        }
                    )
                    raise
                # Pull the just-recorded phase metrics back out of state.json
                # so we can include cost/duration in the completion event.
                snapshot = state_mod.load(state_dir)
                phase_data = (snapshot.get("phases") or {}).get(str(phase_num), {})
                phase_cost = float(phase_data.get("cost_usd") or 0.0)
                run.total_cost_usd += phase_cost
                run.queue.put_nowait(
                    {
                        "type": "phase_complete",
                        "phase": phase_num,
                        "phase_name": phase_name,
                        "cost_usd": phase_cost,
                        "duration_ms": phase_data.get("duration_ms"),
                        "num_turns": phase_data.get("num_turns"),
                    }
                )
            run.status = "complete"
            run.queue.put_nowait(
                {
                    "type": "run_complete",
                    "total_cost_usd": run.total_cost_usd,
                }
            )
        except asyncio.CancelledError:
            run.status = "canceled"
            run.queue.put_nowait({"type": "run_canceled"})
            # Don't re-raise — we want the task to end cleanly.
        except Exception as exc:
            run.status = "error"
            run.error = str(exc)
            run.queue.put_nowait(
                {
                    "type": "run_error",
                    "error": str(exc),
                }
            )
        finally:
            run.ended_at = _now_iso()
            run.current_phase = None
            run._done.set()


async def _run_one_phase(phase_num: int, context: Context) -> None:
    """Mirror of the CLI's _run_phase but without the $EDITOR checkpoint
    and with phase-result recording inlined. Imported lazily so the
    server's import path doesn't pull in every phase module on
    server start."""
    name = phase_name_from_number(phase_num)
    if name == "analyze":
        from instantdemo.phases import analyze
        runner = analyze.run
    elif name == "narrate":
        from instantdemo.phases import narrate
        runner = narrate.run
    elif name == "gather":
        from instantdemo.phases import gather
        runner = gather.run
    elif name == "script":
        from instantdemo.phases import script
        runner = script.run
    elif name == "validate":
        from instantdemo.phases import validate
        runner = validate.run
    else:
        raise AssertionError(f"unreachable: phase {name}")
    with state_mod.phase_run(context.state_dir, phase_num):
        await runner(context)


def _json_dumps(obj: Any) -> str:
    """sse-starlette wants a string for the data field."""
    import json
    return json.dumps(obj, default=str)


# Expose the manager via the FastAPI app's state. The lifespan in
# app.py creates the manager and tears it down. Routes look it up
# from request.app.state.run_manager.


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def _manager(request: Request) -> RunManager:
    manager = getattr(request.app.state, "run_manager", None)
    if manager is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="RunManager not initialized; FastAPI lifespan should have set it",
        )
    return manager


@router.post("/runs", response_model=RunInfo, status_code=status.HTTP_202_ACCEPTED)
async def post_run(request_body: RunRequest, request: Request) -> RunInfo:
    manager = _manager(request)
    run = await manager.start_run(request_body)
    return RunInfo(run_id=run.run_id, phases=run.phases, started_at=run.started_at)


@router.get("/runs/{run_id}", response_model=RunStatus)
async def get_run(run_id: str, request: Request) -> RunStatus:
    manager = _manager(request)
    return manager.get_status(run_id)


@router.get("/runs/{run_id}/stream")
async def stream_run(run_id: str, request: Request) -> EventSourceResponse:
    manager = _manager(request)
    return EventSourceResponse(manager.stream_events(run_id))


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str, request: Request) -> dict[str, bool]:
    manager = _manager(request)
    await manager.cancel(run_id)
    return {"ok": True}
