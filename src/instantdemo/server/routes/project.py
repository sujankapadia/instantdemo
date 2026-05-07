"""Project-level API: read the current project's `.instantdemo/state.json`,
phase artifacts, and the rendered video.

The "current project" is the directory the GUI is rooted in. By default
that's the cwd of `instantdemo serve`; it can be overridden via the
`INSTANTDEMO_PROJECT_DIR` env var (set by `instantdemo serve --project PATH`).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Path as PathParam
from fastapi.responses import FileResponse
from pydantic import BaseModel

from instantdemo import state as state_mod


router = APIRouter(prefix="/api", tags=["project"])


PhaseStatus = Literal["pending", "in_progress", "completed", "error"]
PhaseNumber = Literal[1, 2, 3, 4, 5]
ArtifactFormat = Literal["markdown", "json"]


class PhaseState(BaseModel):
    """Per-phase state, as recorded in state.json."""

    status: PhaseStatus | None = None
    started_at: str | None = None
    completed_at: str | None = None
    cost_usd: float | None = None
    duration_ms: int | None = None
    num_turns: int | None = None


class ProjectState(BaseModel):
    """Current project's state, derived from `.instantdemo/state.json`.

    `exists=False` means there is no `state.json` in the project directory
    yet. Frontend renders an empty/onboarding state in that case.
    """

    exists: bool
    name: str
    project_dir: str
    url: str | None = None
    describe: str | None = None
    session_id: str | None = None
    created_at: str | None = None
    phases: dict[str, PhaseState] = {}


class ArtifactResponse(BaseModel):
    """A phase's artifact contents.

    `exists=False` when the phase hasn't run yet (no file on disk). The
    frontend renders an empty placeholder in that case rather than handle
    a 404.
    """

    phase: PhaseNumber
    format: ArtifactFormat
    exists: bool
    content: str | None = None


def _project_dir() -> Path:
    override = os.environ.get("INSTANTDEMO_PROJECT_DIR")
    return Path(override).resolve() if override else Path.cwd()


def _artifact_path(project_dir: Path, phase: int) -> tuple[Path, ArtifactFormat]:
    """Return the artifact file path and its format for a phase number.

    Phase 4's output is JSON at the project root (`demo-script.json`).
    Phases 1, 2, 3, 5 are markdown inside `.instantdemo/`.
    """
    if phase == 4:
        return project_dir / "demo-script.json", "json"
    return project_dir / ".instantdemo" / f"phase{phase}.md", "markdown"


@router.get("/project", response_model=ProjectState)
def get_project() -> ProjectState:
    pdir = _project_dir()
    state_dir = pdir / ".instantdemo"
    state_path = state_dir / state_mod.STATE_FILENAME

    name = pdir.name

    if not state_path.exists():
        return ProjectState(exists=False, name=name, project_dir=str(pdir))

    raw = state_mod.load(state_dir)
    phases_raw = raw.get("phases", {}) or {}
    phases = {key: PhaseState(**value) for key, value in phases_raw.items()}

    return ProjectState(
        exists=True,
        name=name,
        project_dir=str(pdir),
        url=raw.get("url"),
        describe=raw.get("describe"),
        session_id=raw.get("session_id"),
        created_at=raw.get("created_at"),
        phases=phases,
    )


@router.get("/project/artifacts/{phase}", response_model=ArtifactResponse)
def get_artifact(
    phase: int = PathParam(..., ge=1, le=5),
) -> ArtifactResponse:
    pdir = _project_dir()
    path, fmt = _artifact_path(pdir, phase)

    # phase has been validated 1..5 by the path constraint; cast for the
    # Pydantic literal type.
    phase_typed: PhaseNumber = phase  # type: ignore[assignment]

    if not path.exists():
        return ArtifactResponse(
            phase=phase_typed,
            format=fmt,
            exists=False,
            content=None,
        )

    return ArtifactResponse(
        phase=phase_typed,
        format=fmt,
        exists=True,
        content=path.read_text(),
    )


@router.get("/project/video")
def get_video() -> FileResponse:
    pdir = _project_dir()
    video_path = pdir / "demo.mp4"
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="No demo.mp4 in project directory")
    # FileResponse handles HTTP Range requests automatically, which lets
    # the <video> element seek into the stream.
    # Don't set `filename=` — it adds `Content-Disposition: attachment`
    # which is harmless for <video> but inappropriate for inline playback.
    return FileResponse(
        path=str(video_path),
        media_type="video/mp4",
    )
