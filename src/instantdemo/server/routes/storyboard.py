"""Storyboard API (M2): serve the canonical storyboard document and
accept narration edits at the review gate.

The storyboard is UPSTREAM-OF-RENDER truth: edits here flow into the
next [5,6] render via the deterministic Phase 5 projection. Once a
demo is rendered, narration fixes to the EXISTING video go through
/api/segments (which edits demo-script.json and re-renders audio);
a storyboard PATCH after render is allowed but only takes effect on
the next render run. M4's feedback loop reconciles the two surfaces.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict

from instantdemo import state as state_mod
from instantdemo import storyboard as storyboard_mod

router = APIRouter(prefix="/api", tags=["storyboard"])


class StoryboardResponse(BaseModel):
    """`exists=False` (not a 404) when no storyboard.json yet — the
    frontend renders a placeholder, matching SegmentsResponse and
    ArtifactResponse conventions. The doc is passed through raw."""

    exists: bool
    storyboard: dict[str, Any] | None = None


class ScenePatch(BaseModel):
    narration: str


class SceneResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    index: int
    title: str
    narration: str
    action: str
    status: str | None = None


def _project_dir() -> Path:
    override = os.environ.get("INSTANTDEMO_PROJECT_DIR")
    return Path(override).resolve() if override else Path.cwd()


def _state_dir() -> Path:
    return _project_dir() / ".instantdemo"


@router.get("/project/storyboard", response_model=StoryboardResponse)
def get_storyboard() -> StoryboardResponse:
    path = storyboard_mod.path_for(_state_dir())
    if not path.exists():
        return StoryboardResponse(exists=False)
    return StoryboardResponse(
        exists=True, storyboard=json.loads(path.read_text())
    )


@router.patch(
    "/project/storyboard/scenes/{scene_id}", response_model=SceneResponse
)
def patch_scene_narration(
    scene_id: str, patch: ScenePatch, request: Request
) -> SceneResponse:
    """Narration-only scene edit at the storyboard gate (M2).

    Appends a revision entry (phase 0 = user) and re-renders the
    phase4.md view so the power-mode artifact stays consistent.
    Scene add/remove/reorder is deliberately NOT supported here —
    structural changes are M4+ territory.
    """
    # A concurrent [2,3,4] run writes storyboard.json — refuse edits
    # while any run is active (the segments.py precedent).
    manager = getattr(request.app.state, "run_manager", None)
    active = getattr(manager, "active", None)
    if active is not None and active.status in (
        "running", "starting", "paused"
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="a run is in progress; wait for it to finish",
        )

    state_dir = _state_dir()
    try:
        doc = storyboard_mod.load(state_dir)
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="no storyboard yet — run the pipeline first",
        )

    scene = next(
        (s for s in doc.get("scenes", []) if s.get("id") == scene_id), None
    )
    if scene is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no scene {scene_id!r}",
        )

    new_narration = patch.narration
    if new_narration == scene.get("narration", ""):
        return SceneResponse(**scene)  # no-op: don't write or revise

    scene.setdefault("revisions", []).append({
        "type": "narration",
        "from": scene.get("narration", ""),
        "to": new_narration,
        "reason": "user edit at storyboard gate",
        "iteration": 0,
        "phase": 0,
    })
    scene["narration"] = new_narration
    storyboard_mod.save(state_dir, doc)

    # Keep the power-mode artifact consistent with the canonical doc.
    findings = (
        (state_mod.load(state_dir).get("phases") or {})
        .get("4", {})
        .get("explore_findings")
    )
    phase4_view = state_dir / "phase4.md"
    if phase4_view.exists() or findings:
        phase4_view.write_text(
            storyboard_mod.render_phase4_view(doc, findings)
        )

    return SceneResponse(**scene)
