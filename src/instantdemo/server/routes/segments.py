"""Per-segment editing + audio-only re-render.

Two endpoints:

  PATCH /api/segments/{i}                     — update narration in script
  POST  /api/segments/{i}/re-render-audio     — regenerate audio + remux

This is the M3 iteration loop: edit narration → click re-render →
~10–20 seconds later, the same demo.mp4 plays with new voice over the
unchanged visuals. Visual frames stay frozen because we copy the video
stream without re-encoding; only the audio track is replaced.

v1 limitation (worth knowing): we don't yet detect or block when the
new narration is significantly longer than the segment's original
slot. ffmpeg's `-shortest` truncates the longer stream during mux, so
audio that overflows the video gets cut off at the tail. M3's
Iteration 20 polish addresses overflow detection / handling.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Path as PathParam, Request, status
from pydantic import BaseModel


router = APIRouter(prefix="/api", tags=["segments"])


class SegmentPatch(BaseModel):
    """Body of PATCH /api/segments/{i}.

    Only narration is editable in v1. pause_after_ms / structural fields
    require the power-user JSON editor (issue #13) or a full re-run.
    """

    narration: str


class SegmentResponse(BaseModel):
    """Returned from PATCH /api/segments/{i} — the updated segment.

    Uses extra=allow at the call site so action-specific fields
    (selector, url, etc.) pass through.
    """

    index: int
    action: str
    narration: str


class ReRenderResult(BaseModel):
    """Returned from POST /api/segments/{i}/re-render-audio."""

    ok: bool
    duration_ms: int
    new_audio_duration_ms: int
    overflow: bool


def _project_dir() -> Path:
    """Same resolution rule as the other route modules."""
    override = os.environ.get("INSTANTDEMO_PROJECT_DIR")
    return Path(override).resolve() if override else Path.cwd()


def _load_script(project: Path) -> tuple[Path, dict[str, Any]]:
    script_path = project / "demo-script.json"
    if not script_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="demo-script.json not found in project directory",
        )
    try:
        return script_path, json.loads(script_path.read_text())
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"demo-script.json is not valid JSON: {exc}",
        ) from exc


def _resolve_segment(
    script: dict[str, Any], index: int
) -> dict[str, Any]:
    segments = script.get("segments") or []
    if not 0 <= index < len(segments):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"segment index {index} out of range (0..{len(segments) - 1})",
        )
    return segments[index]


@router.patch(
    "/segments/{segment_index}",
    response_model=SegmentResponse,
)
def patch_segment(
    patch: SegmentPatch,
    segment_index: int = PathParam(..., ge=0),
) -> SegmentResponse:
    """Update a segment's narration in demo-script.json. Other fields
    are out of scope for v1 — see issue #13 for the power-user JSON
    editor and #16 for flow-editing."""
    project = _project_dir()
    script_path, script = _load_script(project)
    segment = _resolve_segment(script, segment_index)

    segment["narration"] = patch.narration
    script_path.write_text(json.dumps(script, indent=2) + "\n")

    return SegmentResponse(
        index=segment_index,
        action=segment.get("action", ""),
        narration=segment["narration"],
    )


@router.post(
    "/segments/{segment_index}/re-render-audio",
    response_model=ReRenderResult,
)
async def re_render_audio_endpoint(
    request: Request,
    segment_index: int = PathParam(..., ge=0),
) -> ReRenderResult:
    """Regenerate audio for ALL segments via Kokoro and remux the
    existing demo.mp4 with the new audio track. Video frames stay
    frozen.

    Although the user only edited one segment, we regenerate every
    segment's WAV (no audio cache in v1 per the iteration scope).
    Cost: ~3s per segment × N segments + ~5s ffmpeg = ~20s for a
    typical 15-segment demo.

    Single-active operation: refuses with 409 if a run is in progress
    on the run manager (concurrent writes to demo.mp4 would trample).
    """
    project = _project_dir()
    script_path, script = _load_script(project)
    segments = script.get("segments") or []
    _resolve_segment(script, segment_index)  # validates index

    video_path = project / "demo.mp4"
    if not video_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="demo.mp4 not found; render the demo first",
        )

    # Don't run concurrent with a multi-phase run — both write demo.mp4.
    manager = getattr(request.app.state, "run_manager", None)
    if manager is not None and manager.active is not None:
        if manager.active.status in ("running", "starting", "paused"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="a run is in progress; wait for it to finish or cancel it",
            )

    # Run the heavy lifting in a worker thread so we don't block the
    # FastAPI event loop. asyncio.to_thread runs sync work in the
    # default executor and awaits its result.
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        _do_re_render_audio,
        project,
        segments,
        segment_index,
        video_path,
    )


def _load_recorded_durations(
    state_dir: Path, expected_len: int
) -> list[float] | None:
    """Read `recorded_clean_duration_s` per segment from an existing
    segment-timing.json, if present and well-formed. Returns None if
    the file is missing, malformed, length-mismatched, or doesn't
    have the field on every segment (e.g. produced by an older
    renderer that predates issue #19).
    """
    timing_path = state_dir / "segment-timing.json"
    if not timing_path.exists():
        return None
    try:
        data = json.loads(timing_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    raw_segments = data.get("segments") or []
    if len(raw_segments) != expected_len:
        return None
    out: list[float] = []
    for s in raw_segments:
        value = s.get("recorded_clean_duration_s")
        if not isinstance(value, (int, float)):
            return None
        out.append(float(value))
    return out


def _do_re_render_audio(
    project: Path,
    segments: list[dict[str, Any]],
    segment_index: int,
    video_path: Path,
) -> ReRenderResult:
    """Synchronous worker for the re-render-audio endpoint."""
    from instantdemo.render import (
        _write_segment_timing,
        generate_audio_kokoro,
        get_audio_duration,
        remux_audio_only,
    )

    state_dir = project / ".instantdemo"
    state_dir.mkdir(parents=True, exist_ok=True)

    # Preserve recorded clean durations across audio-only re-renders.
    # We're not re-recording, so the original video segment lengths
    # haven't changed — but _write_segment_timing rebuilds the file
    # from scratch, so we need to re-pass them. See issue #19.
    recorded_durations = _load_recorded_durations(state_dir, len(segments))

    tmp_dir = Path(tempfile.mkdtemp(prefix="instantdemo-re-render-"))
    try:
        # Generate audio for ALL segments (no cache in v1).
        # Default voice/speed match the renderer's defaults.
        clips = generate_audio_kokoro(segments, tmp_dir, "af_heart", 1.0)
        clip_durations = [get_audio_duration(c) for c in clips]

        # Atomic write: render to tmp file then move into place.
        output_tmp = tmp_dir / "demo.mp4"
        remux_audio_only(
            existing_video=video_path,
            audio_clips=clips,
            clip_durations=clip_durations,
            segments=segments,
            output_path=output_tmp,
            tmp_dir=tmp_dir,
        )
        shutil.move(str(output_tmp), str(video_path))

        # Update segment-timing.json so click-to-seek lands on the right
        # content after the edit. Uses the same helper the renderer uses
        # so the format stays in sync.
        _write_segment_timing(
            state_dir, segments, clip_durations, video_path.name,
            recorded_durations_s=recorded_durations,
        )

        # Compute response fields.
        new_audio_duration_s = clip_durations[segment_index]
        edited_segment = segments[segment_index]
        pause_s = (edited_segment.get("pause_after_ms") or 0) / 1000
        slot_s = max(new_audio_duration_s, pause_s)
        # Approximate "overflow" for the response: if the new audio is
        # longer than the segment's pause_after_ms slot, the slot grew
        # because of audio length, and downstream alignment may drift.
        # Real overflow detection (vs. original recording duration)
        # comes in M3 polish.
        overflow = new_audio_duration_s > pause_s and pause_s > 0

        return ReRenderResult(
            ok=True,
            duration_ms=int(slot_s * 1000),
            new_audio_duration_ms=int(new_audio_duration_s * 1000),
            overflow=overflow,
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
