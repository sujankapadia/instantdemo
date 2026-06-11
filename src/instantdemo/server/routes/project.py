"""Project-level API: read the current project's `.instantdemo/state.json`,
phase artifacts, and the rendered video.

The "current project" is the directory the GUI is rooted in. By default
that's the cwd of `instantdemo serve`; it can be overridden via the
`INSTANTDEMO_PROJECT_DIR` env var (set by `instantdemo serve --project PATH`).
"""

from __future__ import annotations

import json
import re
import os
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Path as PathParam
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict

from instantdemo import state as state_mod


router = APIRouter(prefix="/api", tags=["project"])


PhaseStatus = Literal["pending", "in_progress", "completed", "error", "canceled"]
PhaseNumber = Literal[1, 2, 3, 4, 5, 6]
ArtifactFormat = Literal["markdown", "json"]


class PhaseState(BaseModel):
    """Per-phase state, as recorded in state.json."""

    model_config = ConfigDict(extra="allow")

    status: PhaseStatus | None = None
    started_at: str | None = None
    completed_at: str | None = None
    cost_usd: float | None = None
    duration_ms: int | None = None
    num_turns: int | None = None
    # Phase 4 (Explore) records structured findings here when the
    # agent emits a JSON block. Used by the frontend's triage panel
    # to surface per-segment failures with suggested fixes. See
    # issue #48.
    explore_findings: dict[str, Any] | None = None
    explore_overall: str | None = None  # "OK" or "BLOCKED"
    # Phase 1 (Understand, explore-first since M1) records its
    # proposed demo intent + visited screens + warnings here. The
    # frontend's intent-confirmation card reads these.
    intent_proposal: dict[str, Any] | None = None
    screens: list[dict[str, Any]] | None = None
    warnings: list[str] | None = None


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
    # Source path the agent reads from during Phase 1 / Phase 3.
    # Persisted in state.json so Regenerate can prefill it without
    # the user re-typing the path.
    source: str | None = None
    # Current intent.json contents (or synthesized from describe when
    # intent.json doesn't exist yet). Frontend uses this to prefill
    # the Regenerate form.
    intent: dict[str, Any] | None = None
    session_id: str | None = None
    created_at: str | None = None
    phases: dict[str, PhaseState] = {}
    # Set by the run manager while a multi-phase run is active. Cleared
    # on terminal events. The GUI uses this to detect that a run is
    # still in flight after a browser refresh.
    current_run_id: str | None = None
    # Two-run intent confirmation (M1): false after a phases-[1]-only
    # exploration run; true once a run with intent + phases >= 2
    # starts. The GUI shows the confirmation card when a proposal
    # exists and this is false — derived server-side so reloads
    # re-show the card.
    intent_confirmed: bool = False
    # Storyboard gate (M2): false after the plan/inspect/rehearse leg
    # ([2,3,4] or any re-rehearse); true once a run including phase 5
    # or 6 starts (approve / re-render / Regenerate). Gate visibility
    # derives from this — reload-safe.
    storyboard_approved: bool = False


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


class Segment(BaseModel):
    """One segment from demo-script.json plus joined timing.

    Action-specific fields (selector, url, pixels, wait_for, frame, key,
    expression, value, ...) are passed through as-is via extra="allow"
    so the API doesn't have to be updated when the script schema gains
    new optional fields.
    """

    model_config = ConfigDict(extra="allow")

    index: int
    action: str
    narration: str = ""
    pause_after_ms: int | None = None

    # Joined from segment-timing.json. Null when timing file is absent.
    start_s: float | None = None
    end_s: float | None = None
    audio_duration_s: float | None = None
    # Actual clean-window video frames captured for this segment (#19).
    # Null when timing is absent or was produced before #19.
    recorded_clean_duration_s: float | None = None
    # True when the segment's audio is longer than its recorded video
    # frames — ffmpeg's `-shortest` will truncate the audio at mux time.
    # Null when we can't tell (either field missing).
    audio_overflows: bool | None = None


class SegmentsResponse(BaseModel):
    """Segment list for the GUI's right-pane segments view.

    `exists=False` means demo-script.json is missing (e.g. Phase 4
    hasn't run yet). `has_timing=False` means the script is present but
    the renderer hasn't emitted segment-timing.json — segments still
    come back, just without start_s/end_s/audio_duration_s populated.
    """

    exists: bool
    has_timing: bool
    total_duration_s: float | None = None
    segments: list[Segment] = []


def _project_dir() -> Path:
    override = os.environ.get("INSTANTDEMO_PROJECT_DIR")
    return Path(override).resolve() if override else Path.cwd()


def _artifact_path(project_dir: Path, phase: int) -> tuple[Path, ArtifactFormat]:
    """Return the artifact file path and its format for a phase number.

    Phase 5's output is JSON at the project root (`demo-script.json`).
    Phases 1, 2, 3, 4, 6 are markdown inside `.instantdemo/`.
    """
    if phase == 5:
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

    # Load intent (or synthesize from describe for legacy projects)
    # so the Regenerate form can prefill all current intent fields.
    from instantdemo import intent as intent_mod
    intent_obj = intent_mod.load_or_synthesize(pdir, raw.get("describe"))

    return ProjectState(
        exists=True,
        name=name,
        project_dir=str(pdir),
        url=raw.get("url"),
        describe=raw.get("describe"),
        source=raw.get("source"),
        intent={
            "goal": intent_obj.goal,
            "audience": intent_obj.audience,
            "tone": intent_obj.tone,
            "focus": intent_obj.focus,
            "excludes": intent_obj.excludes,
            "addenda": intent_obj.addenda,
        },
        session_id=raw.get("session_id"),
        created_at=raw.get("created_at"),
        phases=phases,
        current_run_id=raw.get("current_run_id"),
        intent_confirmed=bool(raw.get("intent_confirmed", False)),
        storyboard_approved=bool(raw.get("storyboard_approved", False)),
    )


@router.get("/project/artifacts/{phase}", response_model=ArtifactResponse)
def get_artifact(
    phase: int = PathParam(..., ge=1, le=6),
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


def _load_timing(state_dir: Path) -> dict[str, Any] | None:
    """Read segment-timing.json if present, else None."""
    path = state_dir / "segment-timing.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


@router.get("/project/segments", response_model=SegmentsResponse)
def get_segments() -> SegmentsResponse:
    pdir = _project_dir()
    script_path = pdir / "demo-script.json"
    state_dir = pdir / ".instantdemo"

    if not script_path.exists():
        return SegmentsResponse(exists=False, has_timing=False)

    try:
        script = json.loads(script_path.read_text())
    except (json.JSONDecodeError, OSError):
        return SegmentsResponse(exists=False, has_timing=False)

    raw_segments = script.get("segments", []) or []

    timing = _load_timing(state_dir)
    timing_by_index: dict[int, dict[str, Any]] = {}
    total_duration_s: float | None = None
    timing_used = False

    if timing:
        timing_segs = timing.get("segments", []) or []
        # Heuristic: timing is stale when its segment count doesn't match
        # the current script (user edited demo-script.json after the last
        # render, etc.). Ignore stale timing rather than serve stamps that
        # point at the wrong content. Doesn't catch in-place edits that
        # preserve segment count; a checksum-based check could but isn't
        # worth the complexity until it bites.
        if len(timing_segs) == len(raw_segments):
            timing_used = True
            for entry in timing_segs:
                idx = entry.get("index")
                if isinstance(idx, int):
                    timing_by_index[idx] = entry
            total = timing.get("total_duration_s")
            total_duration_s = (
                float(total) if isinstance(total, (int, float)) else None
            )

    segments: list[Segment] = []
    for i, raw in enumerate(raw_segments):
        merged: dict[str, Any] = {**raw, "index": i}
        t = timing_by_index.get(i)
        if t is not None:
            merged["start_s"] = t.get("start_s")
            merged["end_s"] = t.get("end_s")
            audio_s = t.get("audio_duration_s")
            merged["audio_duration_s"] = audio_s
            recorded_s = t.get("recorded_clean_duration_s")
            if isinstance(recorded_s, (int, float)):
                merged["recorded_clean_duration_s"] = float(recorded_s)
                if isinstance(audio_s, (int, float)):
                    merged["audio_overflows"] = (
                        float(audio_s) > float(recorded_s)
                    )
        segments.append(Segment(**merged))

    return SegmentsResponse(
        exists=True,
        has_timing=timing_used,
        total_duration_s=total_duration_s,
        segments=segments,
    )


_EXPLORATION_FILENAME_RE = re.compile(r"^[A-Za-z0-9._-]+\.png$")


def _exploration_dir(pdir: Path) -> Path:
    return pdir / ".instantdemo" / "exploration"


@router.get("/project/exploration")
def list_exploration() -> dict[str, list[str]]:
    """Sorted exploration screenshot filenames (Phase 1, M1).

    The frontend filmstrip merges this with live `screenshot` SSE
    events so a page reload still shows the strip.
    """
    exp_dir = _exploration_dir(_project_dir())
    if not exp_dir.is_dir():
        return {"files": []}
    return {
        "files": sorted(
            p.name
            for p in exp_dir.iterdir()
            if p.is_file() and _EXPLORATION_FILENAME_RE.match(p.name)
        )
    }


@router.get("/project/rehearsal/{filename}")
def get_rehearsal_shot(filename: str) -> FileResponse:
    """Serve one Phase 4 rehearsal screenshot (M2 storyboard
    thumbnails). Same whitelist + containment defenses as the
    exploration endpoint. No listing endpoint — the storyboard doc
    carries `rehearsal_screenshot` per scene."""
    if not _EXPLORATION_FILENAME_RE.match(filename):
        raise HTTPException(status_code=400, detail="invalid filename")
    shots_dir = _project_dir() / ".instantdemo" / "rehearsal"
    path = (shots_dir / filename).resolve()
    if not path.is_relative_to(shots_dir.resolve()) or not path.exists():
        raise HTTPException(status_code=404, detail="no such screenshot")
    return FileResponse(path=str(path), media_type="image/png")


@router.get("/project/exploration/{filename}")
def get_exploration_shot(filename: str) -> FileResponse:
    """Serve one exploration screenshot. Filenames are whitelisted by
    regex and resolved-path checked — belt and suspenders against
    traversal."""
    if not _EXPLORATION_FILENAME_RE.match(filename):
        raise HTTPException(status_code=400, detail="invalid filename")
    exp_dir = _exploration_dir(_project_dir())
    path = (exp_dir / filename).resolve()
    if not path.is_relative_to(exp_dir.resolve()) or not path.exists():
        raise HTTPException(status_code=404, detail="no such screenshot")
    return FileResponse(path=str(path), media_type="image/png")


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
