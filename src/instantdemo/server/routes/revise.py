"""The whole-demo style/pace pass (M4): one instruction, one
interpretation, one revision.

POST /api/project/revise {instruction} →
  - interpret via an SDK call with NO tools (a `style-*` session id
    falls outside PHASE_TOOLS, so the PreToolUse hook denies every
    tool — the call is pure language work on the provided narrations)
  - snapshot a take BEFORE mutating anything
  - apply (narration rewrites and/or pause scaling) to
    demo-script.json, best-effort storyboard sync
  - ONE audio-only re-render in the project voice
  - respond with the studio's explanation + first changed scene so
    the GUI can play the change (felt, not reported)

Voice-identity and structural instructions are answered, not
executed (pointer to Voice settings / the regenerate door). Faster
pacing is written but needs a re-record — never silently spent.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from instantdemo import metrics as metrics_mod
from instantdemo import prompts, revise, storyboard, takes
from instantdemo import state as state_mod
from instantdemo.intent import load_or_synthesize
from instantdemo.phases import Context, run_structured_query

router = APIRouter(prefix="/api", tags=["revise"])


class ReviseRequest(BaseModel):
    instruction: str


class ReviseResponse(BaseModel):
    kind: str
    explanation: str
    suggestion: str | None = None
    rewrites_applied: int = 0
    pace_factor: float | None = None
    needs_rerecord: bool = False
    first_changed_index: int | None = None
    take_n: int | None = None
    storyboard_synced: bool = True
    cost_usd: float = 0.0


def _project_dir() -> Path:
    override = os.environ.get("INSTANTDEMO_PROJECT_DIR")
    return Path(override).resolve() if override else Path.cwd()


def _build_prompt(
    instruction: str, segments: list[dict[str, Any]], project: Path
) -> str:
    intent = load_or_synthesize(project, None)
    lines = [f"The director's instruction: {instruction}", ""]
    if intent.goal:
        lines.append(f"The film's brief: {intent.goal}")
    if intent.tone:
        lines.append(f"Tone: {intent.tone}")
    if intent.audience:
        lines.append(f"Audience: {intent.audience}")
    lines += ["", "The narration, scene by scene:"]
    for i, seg in enumerate(segments, start=1):
        narration = (seg.get("narration") or "").strip() or "(silent)"
        lines.append(f"{i}. {narration}")
    lines += ["", prompts.load("style_pass")]
    return "\n".join(lines)


def _sync_storyboard(
    project: Path, segments: list[dict[str, Any]],
    changed: list[int], instruction: str, *, pace_factor: float | None
) -> bool:
    """Best-effort upstream sync: only when scene/segment counts
    match (never index-map unequal lists)."""
    state_dir = project / ".instantdemo"
    try:
        doc = storyboard.load(state_dir)
    except RuntimeError:
        return False
    scenes = doc.get("scenes", [])
    if len(scenes) != len(segments):
        return False
    for idx in changed:
        scene = scenes[idx]
        revisions = scene.setdefault("revisions", [])
        if pace_factor is None:
            revisions.append({
                "type": "narration",
                "from": scene.get("narration", ""),
                "to": segments[idx].get("narration", ""),
                "reason": instruction,
                "iteration": 0,
                "phase": 0,
            })
            scene["narration"] = segments[idx].get("narration", "")
        else:
            revisions.append({
                "type": "pause_after_ms",
                "from": str(scene.get("pause_after_ms", "")),
                "to": str(segments[idx].get("pause_after_ms", "")),
                "reason": instruction,
                "iteration": 0,
                "phase": 0,
            })
            scene["pause_after_ms"] = segments[idx].get("pause_after_ms")
    storyboard.save(state_dir, doc)
    return True


@router.post("/project/revise", response_model=ReviseResponse)
async def revise_demo(body: ReviseRequest, request: Request) -> ReviseResponse:
    instruction = body.instruction.strip()
    if not instruction:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="say what you'd like changed",
        )
    project = _project_dir()
    script_path = project / "demo-script.json"
    if not script_path.exists() or not (project / "demo.mp4").exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="there's no film to revise yet",
        )
    script = json.loads(script_path.read_text())
    segments: list[dict[str, Any]] = script.get("segments") or []
    if not segments:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="the script has no scenes",
        )

    manager = request.app.state.run_manager
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
            detail="a revision is already in progress",
        )

    # Bidirectional guard: the dispatcher's current_phase is shared
    # mutable state — set busy BEFORE the first await.
    manager.revise_busy = True
    try:
        await manager._ensure_client(str(project), [project])
        context = Context(
            url="",
            source=project,
            project=project,
            describe=None,
            state_dir=project / ".instantdemo",
            output=project / "demo.mp4",
            tts=None,
            no_edit=True,
            client=manager._client,
            dispatcher=manager._dispatcher,
        )
        payload, result = await run_structured_query(
            context,
            _build_prompt(instruction, segments, project),
            session_id=f"style-{uuid.uuid4().hex[:8]}",
            validate=lambda p: revise.validate_style_payload(
                p, segment_count=len(segments)
            ),
            phase_number=0,
        )
        cost = float(getattr(result, "total_cost_usd", 0.0) or 0.0)
        metrics_mod.append(
            project / ".instantdemo",
            phase_number=0,
            phase_name="style",
            cost_usd=cost,
        )

        kind = payload["kind"]
        explanation = payload["explanation"]
        if kind in ("voice", "structural", "unclear"):
            return ReviseResponse(
                kind=kind,
                explanation=explanation,
                suggestion=payload.get("suggestion"),
                cost_usd=cost,
            )

        # Mutating kinds: the current film becomes restorable history
        # BEFORE anything changes (skipped when the newest take
        # already is the current film).
        take_n = takes.snapshot_unless_current(project, "style")

        changed: list[int] = []
        pace_factor: float | None = None
        needs_rerecord = False
        if kind == "rewrite":
            changed = revise.apply_rewrites(segments, payload["rewrites"])
        else:  # pace
            pace_factor = float(payload["pace_factor"])
            changed = revise.apply_pace(segments, pace_factor)
            needs_rerecord = pace_factor < 1
        script_path.write_text(json.dumps(script, indent=2) + "\n")
        synced = _sync_storyboard(
            project, segments, changed, instruction, pace_factor=pace_factor
        )

        first_changed = changed[0] if changed else None
        if not needs_rerecord and changed:
            # ONE audio-only re-render in the project voice. The
            # take was already snapshotted — take_label=None.
            from .segments import _do_re_render_audio

            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: _do_re_render_audio(
                    project,
                    segments,
                    first_changed or 0,
                    project / "demo.mp4",
                    None,
                ),
            )

        # Keep state.json's describe-side untouched; just confirm the
        # project still loads (cheap sanity for the L5 path).
        state_mod.load(project / ".instantdemo")

        return ReviseResponse(
            kind=kind,
            explanation=explanation,
            rewrites_applied=len(changed) if kind == "rewrite" else 0,
            pace_factor=pace_factor,
            needs_rerecord=needs_rerecord,
            first_changed_index=first_changed,
            take_n=take_n,
            storyboard_synced=synced,
            cost_usd=cost,
        )
    finally:
        manager.revise_busy = False
