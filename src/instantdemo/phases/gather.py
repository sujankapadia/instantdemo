"""Phase 3 — Gather technical details.

Reads the storyboard (created by Phase 2) and augments each scene
with the implementation details needed to render the demo: stable
CSS selectors (with fallbacks), wait conditions, action parameters,
and pacing values. The agent re-explores the frontend source
(Read / Glob / Grep) to find selectors matching each scene's
target_hint.

The agent emits a fenced JSON payload keyed by stable scene ids
(validated — every storyboard scene exactly once — with one
corrective retry). The runner merges the enrichment into
storyboard.json over a field whitelist (narration and title are NOT
mergeable here: Phase 3 must not re-type them) and renders phase3.md
as a human-readable view. Phase 4 verifies the result against the
live app.
"""

from __future__ import annotations

import json

from .. import prompts, storyboard
from . import (
    Context,
    record_phase_result,
    run_structured_query,
    summarize_run,
)


def _scoped_ids(doc: dict, section: str | None) -> list[str] | None:
    """Scene ids in the scoped chapter (M5b), or None when unscoped."""
    if not section:
        return None
    ids = [
        s["id"] for s in doc["scenes"] if s.get("section") == section
    ]
    if not ids:
        raise RuntimeError(f"no chapter named {section!r} in the storyboard")
    return ids


def _scenes_for_prompt(doc: dict, scope_ids: list[str] | None = None) -> str:
    """Compact scene JSON the agent enriches — planning fields only.
    When scoped, only the chapter's scenes are listed."""
    compact = [
        {
            "id": scene["id"],
            "index": scene["index"],
            "title": scene["title"],
            "narration": scene.get("narration", ""),
            "action": scene["action"],
            "target_hint": scene.get("target_hint", ""),
        }
        for scene in doc["scenes"]
        if scope_ids is None or scene["id"] in scope_ids
    ]
    return json.dumps({"scenes": compact}, indent=2)


def _build_prompt(
    doc: dict, url: str, scope_ids: list[str] | None = None,
    section: str | None = None,
) -> str:
    template = prompts.load("phase3")
    scoped_note = (
        (
            f"You are enriching ONE chapter of the storyboard: the "
            f"\"{section}\" chapter — exactly the scenes below, nothing "
            "else. Other chapters are handled in their own passes.\n\n"
        )
        if scope_ids
        else ""
    )
    return (
        f"The app being demoed is running at: {url}\n"
        "\n"
        "Use this base URL for all `goto` scenes. When the narrative\n"
        "references a route like `/active`, combine it with the base URL\n"
        f"to form the full URL ({url}/active). Do NOT use a different\n"
        "port from the codebase configuration — the user has chosen this\n"
        "specific URL.\n"
        "\n"
        f"{scoped_note}"
        "These are the storyboard scenes from Phase 2. Each has a stable\n"
        "`id` — your output is keyed by it.\n"
        "\n"
        "---\n"
        f"{_scenes_for_prompt(doc, scope_ids)}\n"
        "---\n"
        "\n"
        f"{template}"
    )


def _make_validator(doc: dict, scope_ids: list[str] | None = None):
    """Validator closure: id discipline + a dry-run merge that must
    leave the storyboard valid at stage='hypothesized'. When scoped,
    exactly the chapter's ids are expected (M5b)."""
    expected_ids = scope_ids or [scene["id"] for scene in doc["scenes"]]

    def _validate(payload: dict) -> list[str]:
        problems: list[str] = []
        scenes = payload.get("scenes")
        if not isinstance(scenes, list) or not scenes:
            return ["payload must contain a non-empty 'scenes' array"]
        returned_ids = [
            s.get("id") for s in scenes if isinstance(s, dict)
        ]
        missing = [i for i in expected_ids if i not in returned_ids]
        extra = [i for i in returned_ids if i not in expected_ids]
        dupes = {str(i) for i in returned_ids if i and returned_ids.count(i) > 1}
        if missing:
            problems.append(
                f"missing scene ids: {', '.join(missing)} — every input "
                "scene must appear exactly once"
            )
        if extra:
            problems.append(
                f"unknown scene ids: {', '.join(str(i) for i in extra)} — "
                "do not invent or split scenes"
            )
        if dupes:
            problems.append(f"duplicate scene ids: {', '.join(sorted(dupes))}")
        if problems:
            return problems

        # Dry-run the merge on a copy; the merged SCOPED scenes must
        # validate at hypothesized. Only the scenes in scope — during
        # the M7 cold-start loop, later chapters are still bare
        # (planned, no selectors) and must not fail this chapter's
        # validation.
        trial = json.loads(json.dumps(doc))
        _merge(trial, payload)
        scoped_trial = dict(
            trial,
            scenes=[
                s for s in trial["scenes"] if s["id"] in expected_ids
            ],
        )
        problems.extend(
            storyboard.validate_storyboard(scoped_trial, stage="hypothesized")
        )
        return problems

    return _validate


def _merge(doc: dict, payload: dict) -> None:
    """Merge enrichment into scenes by id over the field whitelist."""
    by_id = {scene["id"]: scene for scene in doc["scenes"]}
    for update in payload["scenes"]:
        scene = by_id[update["id"]]
        for field in storyboard.PHASE3_MERGEABLE_FIELDS:
            if field not in update:
                continue
            value = update[field]
            if field in ("selector", "wait_for"):
                value = storyboard.normalize_candidates(value)
                if not value:
                    continue
            if value in (None, ""):
                continue
            scene[field] = value
        scene["status"] = "hypothesized"


async def run_for_section(
    context: Context, doc: dict, section: str | None, session_id: str
):
    """Enrich ONE chapter's scenes (M7): the scoped prompt/validator/
    merge from M5b, parameterized by section instead of reading
    context.section_scope. Returns the call's ResultMessage."""
    scope_ids = _scoped_ids(doc, section) if section else None
    prompt = _build_prompt(doc, context.url, scope_ids, section)
    payload, result = await run_structured_query(
        context,
        prompt,
        session_id,
        validate=_make_validator(doc, scope_ids),
        phase_number=3,
    )
    _merge(doc, payload)
    storyboard.save(context.state_dir, doc)
    if section:
        print(
            f"  Chapter {section!r}: "
            f"{len(scope_ids or [])} scenes hypothesized"
        )
    return result


async def run(context: Context) -> None:
    if context.client is None:
        raise RuntimeError(
            "Phase 3: no agent client provided in context. The CLI is "
            "responsible for creating and passing through a ClaudeSDKClient."
        )

    doc = storyboard.load(context.state_dir)

    artifact = context.phase_artifact(3)
    artifact.parent.mkdir(parents=True, exist_ok=True)

    # Chaptered always (M7): one bounded call per chapter. A scoped
    # revision ([2,3,4] with section_scope) is the single-chapter
    # special case of the same loop.
    if context.section_scope:
        sections: list[str | None] = [context.section_scope]
    else:
        sections = [c["name"] for c in storyboard.chapters(doc)]
        if not sections:
            # Legacy sectionless storyboard (pre-M5a project or old
            # fixture): one full-board leg — the original behavior.
            sections = [None]
    run8 = (context.run_id or "")[:8] or "norun"

    total_cost = 0.0
    total_turns = 0
    result = None
    for k, section in enumerate(sections):
        if context.event_emitter is not None and len(sections) > 1:
            context.event_emitter({
                "type": "chapter_progress",
                "phase": 3,
                "current": k + 1,
                "total": len(sections),
                "name": section,
            })
        result = await run_for_section(
            context, doc, section, f"phase3-{run8}-c{k + 1}"
        )
        total_cost += float(getattr(result, "total_cost_usd", 0.0) or 0.0)
        total_turns += int(getattr(result, "num_turns", 0) or 0)

    artifact.write_text(storyboard.render_phase3_view(doc))
    record_phase_result(
        context, 3, result,
        cost_usd_total=total_cost, num_turns_total=total_turns,
    )
    print(summarize_run(3, artifact, result))
    print(
        f"  (storyboard: {len(doc['scenes'])} scenes hypothesized in "
        f"{len(sections)} chapter(s); phase total ${total_cost:.2f})"
    )
