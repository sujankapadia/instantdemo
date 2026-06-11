"""Takes API (M4): list previous versions, serve their video for the
player's Previous-version toggle, restore one."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from instantdemo import takes as takes_mod

router = APIRouter(prefix="/api", tags=["takes"])


class Take(BaseModel):
    n: int
    label: str = ""
    created_at: str | None = None
    video_exists: bool = False
    # True when this take's video IS the current film (post-render
    # snapshot, nothing revised since) — not a "previous" version.
    is_current: bool = False


class TakesResponse(BaseModel):
    takes: list[Take]


def _project_dir() -> Path:
    override = os.environ.get("INSTANTDEMO_PROJECT_DIR")
    return Path(override).resolve() if override else Path.cwd()


def _reject_during_runs(request: Request) -> None:
    manager = getattr(request.app.state, "run_manager", None)
    active = getattr(manager, "active", None)
    if active is not None and active.status in (
        "running", "starting", "paused"
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="a run is in progress; wait for it to finish",
        )
    if getattr(manager, "revise_busy", False):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="a revision is in progress; wait for it to finish",
        )


@router.get("/project/takes", response_model=TakesResponse)
def get_takes() -> TakesResponse:
    return TakesResponse(
        takes=[Take(**t) for t in takes_mod.list_takes(_project_dir())]
    )


@router.get("/project/takes/{n}/video")
def get_take_video(n: int) -> FileResponse:
    path = takes_mod.take_video_path(_project_dir(), n)
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="that version's video is no longer kept",
        )
    return FileResponse(path=str(path), media_type="video/mp4")


@router.post("/project/takes/{n}/restore", response_model=TakesResponse)
async def restore_take(n: int, request: Request) -> TakesResponse:
    _reject_during_runs(request)
    project = _project_dir()
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, takes_mod.restore, project, n)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    return get_takes()
