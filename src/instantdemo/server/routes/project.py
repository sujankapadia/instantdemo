"""Project-level API: read the current project's `.instantdemo/state.json`.

The "current project" is the directory the GUI is rooted in. By default
that's the cwd of `instantdemo serve`; it can be overridden via the
`INSTANTDEMO_PROJECT_DIR` env var (set by `instantdemo serve --project PATH`).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from instantdemo import state as state_mod


router = APIRouter(prefix="/api", tags=["project"])


PhaseStatus = Literal["pending", "in_progress", "completed", "error"]


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


def _project_dir() -> Path:
    override = os.environ.get("INSTANTDEMO_PROJECT_DIR")
    return Path(override).resolve() if override else Path.cwd()


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
