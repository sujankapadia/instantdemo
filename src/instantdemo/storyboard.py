"""The storyboard contract: the canonical structured artifact for
pipeline phases 2-5.

`.instantdemo/storyboard.json` is the single source of truth for the
demo plan. Phases progressively enrich it:

    Phase 2 (narrate)  creates it — scenes with title/narration/action
                       and a high-level target_hint    (status: planned)
    Phase 3 (gather)   merges selector hypotheses       (hypothesized)
    Phase 4 (explore)  verifies against the live app, applies
                       revisions, records verification  (verified/warn/failed)
    Phase 5 (script)   deterministically projects it to demo-script.json
                       (no agent — see to_demo_script)

Runners own all reads/writes/merges; agents emit fenced JSON blocks
that runners validate and merge. The phaseN.md files are RENDERED
VIEWS generated from this document (render_phaseN_view) so the GUI's
markdown rendering and the CLI's $EDITOR checkpoints keep working.

Style matches actions.py: stdlib-only, plain dicts, validator
functions returning problem lists (no pydantic in pipeline code).
Scene `id`s are runner-assigned ("s1", "s2", ...) from the document's
monotonic `next_scene_seq` and are never reused — future features
(notes, sections, versioned takes) attach to them.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .actions import CANONICAL_ACTIONS

STORYBOARD_FILENAME = "storyboard.json"
VERSION = 1

# Scene fields Phase 3 may merge. Narration/title are deliberately
# absent: Phase 3 must not re-type them (kills a drift channel).
PHASE3_MERGEABLE_FIELDS = (
    "action",
    "url",
    "selector",
    "wait_for",
    "value",
    "key",
    "expression",
    "pixels",
    "pause_after_ms",
    "notes",
)

# Fields whose canonical in-pipeline form is a candidate list
# (primary first, fallbacks after).
_CANDIDATE_FIELDS = ("selector", "wait_for")

_SCENE_STATUSES = ("planned", "hypothesized", "verified", "warn", "failed")

# Lifted from explore.py: first fenced JSON block in agent text.
JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*\n(.*?)\n```", re.DOTALL)

MIGRATION_ERROR = (
    ".instantdemo/storyboard.json not found — this project predates "
    "the storyboard contract. Re-run from Phase 2 (Plan); phase "
    "artifacts will be regenerated."
)


def path_for(state_dir: Path) -> Path:
    return state_dir / STORYBOARD_FILENAME


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load(state_dir: Path) -> dict:
    """Load the storyboard, raising the migration error if absent."""
    path = path_for(state_dir)
    if not path.exists():
        raise RuntimeError(MIGRATION_ERROR)
    return json.loads(path.read_text())


def save(state_dir: Path, doc: dict) -> Path:
    """Persist the document: stamp updated_at, recompute 1-based
    scene indexes from array order."""
    doc["updated_at"] = _now()
    for i, scene in enumerate(doc.get("scenes", []), start=1):
        scene["index"] = i
    path = path_for(state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n")
    return path


def new_document(
    *, title: str, url: str, summary: str = "", provenance: dict | None = None
) -> dict:
    return {
        "version": VERSION,
        "title": title,
        "url": url,
        "summary": summary,
        "created_at": _now(),
        "updated_at": _now(),
        "provenance": provenance or {},
        "next_scene_seq": 1,
        "scenes": [],
    }


def add_scene(
    doc: dict,
    *,
    title: str,
    narration: str,
    action: str,
    target_hint: str = "",
    **fields: Any,
) -> dict:
    """Append a scene, assigning its stable id from next_scene_seq."""
    seq = doc.get("next_scene_seq", len(doc.get("scenes", [])) + 1)
    scene: dict[str, Any] = {
        "id": f"s{seq}",
        "index": len(doc["scenes"]) + 1,
        "title": title,
        "narration": narration,
        "action": action,
        "target_hint": target_hint,
        "status": "planned",
        "revisions": [],
    }
    for key, value in fields.items():
        if value is not None:
            scene[key] = value
    for field in _CANDIDATE_FIELDS:
        if field in scene:
            scene[field] = normalize_candidates(scene[field])
    doc["next_scene_seq"] = seq + 1
    doc["scenes"].append(scene)
    return scene


def normalize_candidates(value: Any) -> list[str]:
    """Coerce a selector-ish value (string or list) to the canonical
    candidate-list form: non-empty strings, primary first."""
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    else:
        items = list(value)
    return [str(v).strip() for v in items if str(v).strip()]


def extract_json_block(text: str) -> dict | None:
    """First parseable fenced JSON object in agent text, else None."""
    for match in JSON_BLOCK_RE.finditer(text):
        try:
            parsed = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_storyboard(doc: dict, *, stage: str) -> list[str]:
    """Validate the document for a pipeline stage; return problems
    (empty = valid). Stages are cumulative:

      planned       — structure, unique ids, known actions (post Phase 2)
      hypothesized  — + per-action required fields present (post Phase 3)
      verified      — + every scene verified or warn       (pre Phase 5)
    """
    if stage not in ("planned", "hypothesized", "verified"):
        raise ValueError(f"unknown stage {stage!r}")

    problems: list[str] = []
    if doc.get("version") != VERSION:
        problems.append(f"version must be {VERSION}, got {doc.get('version')!r}")
    scenes = doc.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        problems.append("storyboard has no scenes")
        return problems

    seen_ids: set[str] = set()
    for i, scene in enumerate(scenes, start=1):
        label = f"scene {i} ({scene.get('id', '?')})"
        scene_id = scene.get("id")
        if not scene_id or not isinstance(scene_id, str):
            problems.append(f"scene {i}: missing string id")
        elif scene_id in seen_ids:
            problems.append(f"scene {i}: duplicate id {scene_id!r}")
        else:
            seen_ids.add(scene_id)

        if not isinstance(scene.get("title"), str) or not scene.get("title"):
            problems.append(f"{label}: missing title")
        if not isinstance(scene.get("narration"), str):
            problems.append(f"{label}: narration must be a string (\"\" for silent)")

        action = scene.get("action")
        if action not in CANONICAL_ACTIONS:
            problems.append(
                f"{label}: unknown action {action!r}; allowed: "
                f"{', '.join(sorted(CANONICAL_ACTIONS))}"
            )
            continue

        status = scene.get("status")
        if status not in _SCENE_STATUSES:
            problems.append(f"{label}: unknown status {status!r}")

        if stage in ("hypothesized", "verified"):
            for field in CANONICAL_ACTIONS[action]:
                value = scene.get(field)
                if field in _CANDIDATE_FIELDS:
                    cands = normalize_candidates(value)
                    if not cands:
                        problems.append(
                            f"{label}: action {action!r} requires "
                            f"non-empty {field!r} candidates"
                        )
                elif value in (None, ""):
                    problems.append(
                        f"{label}: action {action!r} requires the "
                        f"{field!r} field"
                    )
            pause = scene.get("pause_after_ms")
            if pause is not None and not isinstance(pause, int):
                problems.append(f"{label}: pause_after_ms must be an integer")

        if stage == "verified" and scene.get("status") not in ("verified", "warn"):
            problems.append(
                f"{label}: status is {scene.get('status')!r} — every "
                "scene must be verified or warn before Phase 5"
            )

    return problems


# ---------------------------------------------------------------------------
# Phase 5 projection
# ---------------------------------------------------------------------------


def to_demo_script(
    doc: dict, *, width: int = 1280, height: int = 720
) -> dict:
    """Deterministically project the storyboard to the demo-script.json
    shape the renderer consumes. Single-candidate selector/wait_for
    project as bare strings (today's emitted convention — render.py's
    _selector_candidates normalizes both forms); multi-candidate as
    arrays, primary first. Notes/titles/status/verification/revisions
    deliberately do not project.
    """
    segments: list[dict] = []
    for scene in doc.get("scenes", []):
        seg: dict[str, Any] = {
            "narration": scene.get("narration", ""),
            "action": scene["action"],
        }
        for field in ("url", "value", "key", "expression", "pixels"):
            value = scene.get(field)
            if value not in (None, ""):
                seg[field] = value
        for field in _CANDIDATE_FIELDS:
            cands = normalize_candidates(scene.get(field))
            if len(cands) == 1:
                seg[field] = cands[0]
            elif cands:
                seg[field] = cands
        if scene.get("pause_after_ms") is not None:
            seg["pause_after_ms"] = scene["pause_after_ms"]
        segments.append(seg)
    return {
        "title": doc.get("title") or "Demo",
        "resolution": {"width": width, "height": height},
        "segments": segments,
    }


# ---------------------------------------------------------------------------
# Rendered views (phaseN.md) — what humans and the GUI see
# ---------------------------------------------------------------------------


def _scene_heading(scene: dict) -> str:
    return f"### Segment {scene['index']} — {scene['title']}"


def _narration_line(scene: dict) -> str:
    narration = scene.get("narration", "")
    shown = f'"{narration}"' if narration else "(silent)"
    return f"- **Narration:** {shown}"


def _candidate_lines(scene: dict, field: str, label: str) -> list[str]:
    cands = normalize_candidates(scene.get(field))
    if not cands:
        return []
    lines = [f"- **{label}:** `{cands[0]}`"]
    if len(cands) > 1:
        fallbacks = ", ".join(f"`{c}`" for c in cands[1:])
        lines.append(f"- **{label} fallbacks:** {fallbacks}")
    return lines


def render_phase2_view(doc: dict, answers: dict[str, str]) -> str:
    """phase2.md: ANSWER block (kept so checkpoints.parse_answer_block
    and the legacy CLI edit path keep working) + narrative plan."""
    lines = [
        "<!-- ANSWER THESE BEFORE CONTINUING -->",
        f"tone: {answers.get('tone', '')}",
        f"audience: {answers.get('audience', '')}",
        f"terminology: {answers.get('terminology', '')}",
        "<!-- /ANSWER -->",
        "",
        "<!-- Rendered view of .instantdemo/storyboard.json — edits to",
        "     prose here do NOT feed forward; edit storyboard.json or",
        "     re-run the phase. The ANSWER block above IS read. -->",
        "",
        f"# {doc.get('title') or 'Demo Narrative Plan'}",
        "",
    ]
    if doc.get("summary"):
        lines += [f"**Flow:** {doc['summary']}", ""]
    lines.append("---")
    for scene in doc.get("scenes", []):
        lines += [
            "",
            _scene_heading(scene),
            f"- **Action:** {scene['action']}",
            _narration_line(scene),
        ]
        if scene.get("target_hint"):
            lines.append(f"- **Target:** {scene['target_hint']}")
    return "\n".join(lines) + "\n"


def render_phase3_view(doc: dict) -> str:
    """phase3.md: per-scene selector hypothesis, today's labeled-row
    format (MarkdownView's custom renderers depend on the
    '### Segment N — title' / '- **Label:** value' shapes)."""
    lines = [
        "<!-- Rendered view of .instantdemo/storyboard.json -->",
        "",
        "# Selector plan",
    ]
    for scene in doc.get("scenes", []):
        lines += ["", _scene_heading(scene)]
        lines.append(f"- **Action:** {scene['action']}")
        lines.append(_narration_line(scene))
        if scene.get("url"):
            lines.append(f"- **URL:** {scene['url']}")
        lines += _candidate_lines(scene, "selector", "Selector")
        lines += _candidate_lines(scene, "wait_for", "wait_for")
        for field, label in (
            ("value", "Value"),
            ("key", "Key"),
            ("pixels", "Pixels"),
            ("expression", "Expression"),
        ):
            if scene.get(field) not in (None, ""):
                lines.append(f"- **{label}:** {scene[field]}")
        if scene.get("pause_after_ms") is not None:
            lines.append(f"- **pause_after_ms:** {scene['pause_after_ms']}")
        if scene.get("notes"):
            lines.append(f"- **Notes:** {scene['notes']}")
    return "\n".join(lines) + "\n"


def render_phase4_view(doc: dict, findings: dict | None) -> str:
    """phase4.md: findings JSON block first (keeps the artifact
    self-documenting and existing assertions green), then the
    phase3-style per-scene block with verification lines."""
    lines = ["<!-- Rendered view of .instantdemo/storyboard.json -->", ""]
    if findings is not None:
        lines += [
            "## Dress-rehearsal findings",
            "",
            "```json",
            json.dumps(findings, indent=2),
            "```",
            "",
        ]
    lines.append("## Verified plan")
    for scene in doc.get("scenes", []):
        lines += ["", _scene_heading(scene)]
        lines.append(f"- **Action:** {scene['action']}")
        lines.append(_narration_line(scene))
        if scene.get("url"):
            lines.append(f"- **URL:** {scene['url']}")
        lines += _candidate_lines(scene, "selector", "Selector")
        lines += _candidate_lines(scene, "wait_for", "wait_for")
        if scene.get("pause_after_ms") is not None:
            lines.append(f"- **pause_after_ms:** {scene['pause_after_ms']}")
        verification = scene.get("verification") or {}
        if verification:
            status = verification.get("status", "?")
            reason = verification.get("reason", "")
            lines.append(f"- **Verified:** {status} — {reason}")
            if verification.get("suggestion"):
                lines.append(
                    f"- **Suggestion:** {verification['suggestion']}"
                )
        for rev in scene.get("revisions", []):
            lines.append(
                f"- **Revised ({rev.get('type', '?')}):** "
                f"`{rev.get('from', '')}` → `{rev.get('to', '')}` "
                f"({rev.get('reason', '')})"
            )
        if scene.get("notes"):
            lines.append(f"- **Notes:** {scene['notes']}")
    return "\n".join(lines) + "\n"
