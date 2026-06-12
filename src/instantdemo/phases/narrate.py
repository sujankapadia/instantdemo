"""Phase 2 — Plan the narrative.

Reads the Phase 1 artifact (analysis text + answer block) and produces
the initial storyboard: scenes with title, draft narration, action,
and a high-level target hint, leading with the payoff. Pure reasoning
over Phase 1 output — no tools. The agent emits a fenced JSON payload
(validated, one corrective retry); the runner creates
.instantdemo/storyboard.json (status: planned) and renders phase2.md
as a human-readable view of it.

Input resolution per field (highest priority wins):
  - flow:         intent.goal → phase1.md answer block → context.describe → ""
  - tone:         intent.tone → phase2.md answer block (legacy) → default "casual"
  - audience:     intent.audience → phase2.md answer block (legacy) → default "non-technical (general user, not a developer)"
  - focus:        intent.focus
  - excludes:     intent.excludes
  - addenda:      intent.addenda

All values are deterministically resolved by `_resolve_inputs` and
templated into the prompt header before the agent sees it. The
agent treats them as facts about the demo, not defaults to
reason about.

The phase2.md answer-block mechanism is retained for CLI users who
prefer editing artifacts in $EDITOR. With #39 the GUI writes
intent.json, which takes priority.
"""

from __future__ import annotations

from .. import prompts, revise, storyboard
from ..actions import CANONICAL_ACTIONS
from ..agent_client import session_id_for_phase
from ..checkpoints import parse_answer_block
from . import (
    Context,
    record_phase_result,
    run_structured_query,
    summarize_run,
)


DEFAULT_TONE = "casual"
DEFAULT_AUDIENCE = "non-technical (general user, not a developer)"


def _resolve_inputs(
    context: Context, phase1_answers: dict[str, str], phase2_answers: dict[str, str]
) -> dict[str, object]:
    intent = context.intent
    return {
        "flow": (
            intent.goal
            or phase1_answers.get("flow", "")
            or context.describe
            or ""
        ).strip(),
        "tone": (
            intent.tone
            or phase2_answers.get("tone", "")
            or DEFAULT_TONE
        ).strip(),
        "audience": (
            intent.audience
            or phase2_answers.get("audience", "")
            or DEFAULT_AUDIENCE
        ).strip(),
        "terminology": (phase2_answers.get("terminology") or "").strip(),
        "focus": list(intent.focus),
        "excludes": list(intent.excludes),
        "addenda": list(intent.addenda),
    }


def _inputs_header(inputs: dict[str, object]) -> list[str]:
    """The deterministic intent header shared by the outline and
    chapter-plan prompts."""
    lines: list[str] = []
    flow = inputs.get("flow", "")
    if flow:
        lines.append(f"The user wants to demo: {flow}")
        lines.append("")
    lines.append(f"Tone: {inputs['tone']}")
    lines.append(f"Audience: {inputs['audience']}")
    terminology = inputs.get("terminology", "")
    if terminology:
        lines.append(f"Terminology to use: {terminology}")
    focus_items = inputs.get("focus") or []
    if focus_items:
        lines.append("Focus on: " + "; ".join(focus_items))  # type: ignore[arg-type]
    excludes_items = inputs.get("excludes") or []
    if excludes_items:
        lines.append("Exclude: " + "; ".join(excludes_items))  # type: ignore[arg-type]
    addenda_items = inputs.get("addenda") or []
    if addenda_items:
        lines.append("Additional guidance:")
        for item in addenda_items:  # type: ignore[union-attr]
            lines.append(f"- {item}")
    return lines


def _build_outline_prompt(phase1_text: str, inputs: dict[str, object]) -> str:
    lines = _inputs_header(inputs)
    lines += [
        "",
        "---",
        "Codebase analysis (from Phase 1):",
        "",
        phase1_text,
        "---",
        "",
        prompts.load("phase2_outline"),
    ]
    return "\n".join(lines)


def _outline_text(outline: dict) -> str:
    """The whole arc, rendered for every chapter-plan prompt so each
    chapter knows the film it belongs to."""
    lines = [f"The film: {outline['title']} — {outline.get('summary', '')}"]
    for i, ch in enumerate(outline["chapters"], start=1):
        lines.append(f"  {i}. {ch['name']} — {ch['purpose']}")
    return "\n".join(lines)


def _build_chapter_plan_prompt(
    outline: dict,
    index: int,
    prev_scene: dict | None,
    phase1_text: str,
    inputs: dict[str, object],
) -> str:
    """One chapter's planning call (M7): the full outline for arc
    awareness, this chapter's purpose, the previous chapter's final
    scene for flow continuity, and the phase2 scene rules."""
    chapter = outline["chapters"][index]
    lines = _inputs_header(inputs)
    lines += [
        "",
        "You are planning ONE CHAPTER of this film. The full outline:",
        "",
        _outline_text(outline),
        "",
        f"Plan chapter {index + 1}: \"{chapter['name']}\" — "
        f"{chapter['purpose']} (around {chapter.get('est_scenes', 4)} "
        "scenes; use what the beat needs).",
        "",
    ]
    if prev_scene is not None:
        narration = prev_scene.get("narration") or "(silent)"
        lines += [
            "The previous chapter's final scene was "
            f"\"{prev_scene['title']}\" ({prev_scene['action']}) with the "
            f"narration: \"{narration}\" — your chapter continues from the "
            "app state and the sentence rhythm that scene leaves behind. "
            "Don't repeat its information or echo its phrasing.",
            "",
        ]
    else:
        lines += [
            "This chapter OPENS the film — your first scene must get the "
            "app to its starting state itself (e.g. goto).",
            "",
        ]
    lines += [
        f"Every scene's `section` must be \"{chapter['name']}\". The "
        "`title` and `summary` fields of your JSON are ignored (the film "
        "keeps its own); only `scenes` is read. Later chapters in the "
        "outline are planned separately — end your chapter in an app "
        "state the next chapter's purpose can start from.",
        "",
        "---",
        "Codebase analysis (from Phase 1):",
        "",
        phase1_text,
        "---",
        "",
        prompts.load("phase2"),
    ]
    return "\n".join(lines)


def _validate_outline(payload: dict) -> list[str]:
    """Validate the outline payload (M7) — the film's arc before any
    scene exists."""
    problems: list[str] = []
    if not isinstance(payload.get("title"), str) or not payload["title"]:
        problems.append("payload must contain a non-empty 'title' string")
    chapters = payload.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        problems.append("payload must contain a non-empty 'chapters' array")
        return problems
    if not (2 <= len(chapters) <= 12):
        problems.append(
            f"{len(chapters)} chapters — outline 2 to 12 beats"
        )
    seen: set[str] = set()
    for i, ch in enumerate(chapters, start=1):
        if not isinstance(ch, dict):
            problems.append(f"chapter {i}: must be an object")
            continue
        name = ch.get("name")
        if not isinstance(name, str) or not name.strip():
            problems.append(f"chapter {i}: missing 'name'")
        elif name in seen:
            problems.append(f"chapter {i}: duplicate name {name!r}")
        else:
            seen.add(name)
        if not isinstance(ch.get("purpose"), str) or not ch["purpose"].strip():
            problems.append(f"chapter {i}: missing 'purpose'")
        est = ch.get("est_scenes")
        if not isinstance(est, int) or not (1 <= est <= 12):
            problems.append(
                f"chapter {i}: 'est_scenes' must be an integer 1-12"
            )
    return problems


def _scoped_validator(section: str):
    """Payload validator for a chapter re-plan (M5b): same per-scene
    rules as a full plan, but every scene must belong to the scoped
    chapter and no doc-level title is required (the doc keeps its
    own)."""

    def validate(payload: dict) -> list[str]:
        problems: list[str] = []
        scenes = payload.get("scenes")
        if not isinstance(scenes, list) or not scenes:
            problems.append("payload must contain a non-empty 'scenes' array")
            return problems
        if len(scenes) > 10:
            problems.append(
                f"{len(scenes)} scenes is too many for one chapter — "
                "keep the chapter focused"
            )
        for i, scene in enumerate(scenes, start=1):
            if not isinstance(scene, dict):
                problems.append(f"scene {i}: must be an object")
                continue
            if not isinstance(scene.get("title"), str) or not scene["title"]:
                problems.append(f"scene {i}: missing 'title'")
            if not isinstance(scene.get("narration"), str):
                problems.append(
                    f"scene {i}: 'narration' must be a string (\"\" for silent)"
                )
            if scene.get("action") not in CANONICAL_ACTIONS:
                problems.append(
                    f"scene {i}: unknown action {scene.get('action')!r}; "
                    f"allowed: {', '.join(sorted(CANONICAL_ACTIONS))}"
                )
            if scene.get("section") != section:
                problems.append(
                    f"scene {i}: 'section' must be {section!r} — you are "
                    "revising ONLY that chapter"
                )
        return problems

    return validate


def replace_chapter_scenes(
    doc: dict, section: str, new_scenes: list[dict]
) -> list[str]:
    """Replace the scoped chapter's scenes in place (M5b). New scenes
    get fresh stable ids via add_scene (appended, then moved into the
    chapter's position); every other scene object is untouched.
    Returns the new scene ids. Pure function (unit-tested)."""
    scenes = doc["scenes"]
    positions = [
        i for i, s in enumerate(scenes) if s.get("section") == section
    ]
    if not positions:
        raise ValueError(f"no chapter named {section!r} in the storyboard")
    start = positions[0]
    pre = scenes[:start]
    post = scenes[positions[-1] + 1 :]
    doc["scenes"] = pre + post  # old chapter out (ids retired, never reused)
    added: list[dict] = []
    for scene in new_scenes:
        added.append(
            storyboard.add_scene(
                doc,
                title=scene["title"],
                narration=scene.get("narration", ""),
                action=scene["action"],
                target_hint=scene.get("target_hint", ""),
                section=section,
            )
        )
    # add_scene appends; move the new block into the chapter's slot.
    doc["scenes"] = pre + added + post
    return [s["id"] for s in added]


def _build_scoped_prompt(
    context: Context, doc: dict, phase1_text: str
) -> str:
    section = context.section_scope
    scenes = doc["scenes"]
    positions = [
        i for i, s in enumerate(scenes) if s.get("section") == section
    ]
    if not positions:
        raise RuntimeError(
            f"Phase 2 (scoped): no chapter named {section!r} in the storyboard"
        )
    provenance = doc.get("provenance") or {}
    lines = [
        f"You are revising ONE CHAPTER of an existing demo film: "
        f"\"{section}\".",
        "",
        f"The director's instruction: {context.section_instruction or '(none given — improve the chapter)'}",
        "",
        f"Tone: {provenance.get('tone') or DEFAULT_TONE}",
        f"Audience: {provenance.get('audience') or DEFAULT_AUDIENCE}",
        "",
        "The chapter's CURRENT scenes (you are replacing these):",
    ]
    for s in (scenes[i] for i in positions):
        narration = s.get("narration") or "(silent)"
        lines.append(
            f"- {s['title']} [{s['action']}] — \"{narration}\""
        )
    before = scenes[positions[0] - 1] if positions[0] > 0 else None
    after = (
        scenes[positions[-1] + 1] if positions[-1] + 1 < len(scenes) else None
    )
    lines.append("")
    if before is not None:
        lines.append(
            f"The scene immediately BEFORE this chapter is "
            f"\"{before['title']}\" ({before['action']}"
            + (f" → {before.get('target_hint')}" if before.get("target_hint") else "")
            + ") — your chapter starts from the app state that scene leaves."
        )
    else:
        lines.append(
            "This chapter OPENS the film — your first scene must get the "
            "app to its starting state itself (e.g. goto)."
        )
    if after is not None:
        lines.append(
            f"The scene immediately AFTER this chapter is "
            f"\"{after['title']}\" ({after['action']}"
            + (f" → {after.get('target_hint')}" if after.get("target_hint") else "")
            + ") — your chapter must leave the app in a state that scene "
            "can run from."
        )
    else:
        lines.append("This chapter CLOSES the film.")
    lines += [
        "",
        "Scenes OUTSIDE this chapter are already verified and recorded — "
        "you cannot change them. Plan ONLY the revised chapter: every "
        f"scene's `section` must be \"{section}\". The `title` and "
        "`summary` fields of your JSON are ignored (the film keeps its "
        "own); only `scenes` is read.",
        "",
        "---",
        "App knowledge (from the original exploration):",
        "",
        phase1_text,
        "---",
        "",
        prompts.load("phase2"),
    ]
    return "\n".join(lines)


async def _run_scoped(context: Context) -> None:
    """Chapter re-plan (M5b): edit the existing storyboard in place —
    the scoped chapter's scenes are replaced; everything else is
    asserted untouched."""
    import json as _json

    phase1 = context.phase_artifact(1)
    phase1_text = phase1.read_text() if phase1.exists() else ""
    doc = storyboard.load(context.state_dir)
    section = context.section_scope
    assert section is not None

    prompt = _build_scoped_prompt(context, doc, phase1_text)
    payload, result = await run_structured_query(
        context,
        prompt,
        session_id_for_phase(2, context.run_id),
        validate=_scoped_validator(section),
        phase_number=2,
    )

    # Out-of-scope scenes must come through byte-identical (modulo
    # index, which save() recomputes).
    def _others_snapshot(d: dict) -> str:
        return _json.dumps(
            [
                {k: v for k, v in s.items() if k != "index"}
                for s in d["scenes"]
                if s.get("section") != section
            ],
            sort_keys=True,
        )

    before_others = _others_snapshot(doc)
    new_ids = replace_chapter_scenes(doc, section, payload["scenes"])
    storyboard.save(context.state_dir, doc)
    if _others_snapshot(doc) != before_others:
        raise RuntimeError(
            "Phase 2 (scoped): scenes outside the chapter changed — refusing"
        )
    problems = storyboard.validate_storyboard(doc, stage="planned")
    if problems:
        raise RuntimeError(
            "Phase 2 (scoped): replaced storyboard invalid: "
            + "; ".join(problems)
        )

    artifact = context.phase_artifact(2)
    artifact.parent.mkdir(parents=True, exist_ok=True)
    provenance = doc.get("provenance") or {}
    artifact.write_text(
        storyboard.render_phase2_view(
            doc,
            {
                "tone": provenance.get("tone", ""),
                "audience": provenance.get("audience", ""),
                "terminology": provenance.get("terminology", ""),
            },
        )
    )
    record_phase_result(context, 2, result)
    print(summarize_run(2, artifact, result))
    print(
        f"  (chapter {section!r} re-planned: {len(new_ids)} scenes "
        f"{', '.join(new_ids)})"
    )


CONTINUITY_PROMPT = """You are the script editor reading a demo film's
full narration in one sitting. The chapters were written separately;
your job is to make them read as ONE film.

Look ONLY for:
- repetitive chapter openers ("Now let's...", "Next we..." again and
  again) — vary or drop them
- information repeated across chapters (a fact narrated twice)
- broken transitions (a chapter that ignores where the previous one
  left the viewer)
- global claims duplicated per chapter (e.g. the privacy line said
  three times)

Do NOT restyle, expand, or improve narration that already works.
Return ONLY changed scenes. Keep every rewrite the same approximate
length, spoken plain text, no markup. If the narration already reads
as one film, return an empty rewrites object.

END your response with exactly ONE fenced ```json block:

```json
{
  "kind": "rewrite",
  "explanation": "one sentence on what you smoothed (or that nothing needed it)",
  "rewrites": {"<1-based scene number>": "new narration"}
}
```
"""


def _continuity_validator(scene_count: int):
    """Tolerant wrapper over the style-pass validator (M7): an empty
    rewrites map means "reads fine" and is accepted."""

    def validate(payload: dict) -> list[str]:
        if (
            payload.get("kind") == "rewrite"
            and isinstance(payload.get("rewrites"), dict)
            and not payload["rewrites"]
        ):
            return []
        return revise.validate_style_payload(
            payload, segment_count=scene_count
        )

    return validate


async def _continuity_pass(
    context: Context, doc: dict, outline: dict, session_id: str
) -> tuple[float, int]:
    """One no-tools read-through of the whole narration (M7 beat 3).
    Mutates scene narrations in place via revise.apply_rewrites; the
    caller saves. Returns (cost, turns)."""
    scenes = doc["scenes"]
    lines = [
        "The film's outline:",
        _outline_text(outline),
        "",
        "The narration, scene by scene (chapter markers inline):",
    ]
    current = None
    for i, scene in enumerate(scenes, start=1):
        if scene.get("section") != current:
            current = scene.get("section")
            lines.append(f"--- chapter: {current} ---")
        narration = (scene.get("narration") or "").strip() or "(silent)"
        lines.append(f"{i}. {narration}")
    lines += ["", CONTINUITY_PROMPT]

    payload, result = await run_structured_query(
        context,
        "\n".join(lines),
        session_id,
        validate=_continuity_validator(len(scenes)),
        phase_number=2,
    )
    rewrites = payload.get("rewrites") or {}
    if rewrites:
        changed = revise.apply_rewrites(scenes, rewrites)
        print(
            f"  Continuity pass: smoothed {len(changed)} scene(s) — "
            f"{payload.get('explanation', '')}"
        )
    else:
        print("  Continuity pass: narration reads as one film")
    return (
        float(getattr(result, "total_cost_usd", 0.0) or 0.0),
        int(getattr(result, "num_turns", 0) or 0),
    )


async def run(context: Context) -> None:
    if context.client is None:
        raise RuntimeError(
            "Phase 2: no agent client provided in context. The CLI is "
            "responsible for creating and passing through a ClaudeSDKClient."
        )

    if context.section_scope:
        await _run_scoped(context)
        return

    phase1 = context.phase_artifact(1)
    if not phase1.exists():
        raise RuntimeError(
            f"Phase 1 artifact missing at {phase1}. Run phase 1 first."
        )
    phase1_text = phase1.read_text()
    phase1_answers = parse_answer_block(phase1_text)

    artifact = context.phase_artifact(2)
    artifact.parent.mkdir(parents=True, exist_ok=True)
    phase2_answers = parse_answer_block(artifact.read_text()) if artifact.exists() else {}

    inputs = _resolve_inputs(context, phase1_answers, phase2_answers)
    run8 = (context.run_id or "")[:8] or "norun"
    total_cost = 0.0
    total_turns = 0

    # Beat 1 (M7): the outline — the film's arc before any scene.
    outline, result = await run_structured_query(
        context,
        _build_outline_prompt(phase1_text, inputs),
        f"phase2-{run8}-outline",
        validate=_validate_outline,
        phase_number=2,
    )
    total_cost += float(getattr(result, "total_cost_usd", 0.0) or 0.0)
    total_turns += int(getattr(result, "num_turns", 0) or 0)
    chapters = outline["chapters"]
    print(
        f"  Outline: {len(chapters)} chapters — "
        + ", ".join(ch["name"] for ch in chapters)
    )

    doc = storyboard.new_document(
        title=outline["title"],
        url=context.url,
        summary=outline.get("summary", ""),
        provenance={
            "tone": inputs["tone"],
            "audience": inputs["audience"],
            "terminology": inputs["terminology"],
            "intent_goal": inputs["flow"],
        },
    )

    # Beat 2: plan each chapter as its own bounded call. Whole-chapter
    # appends keep contiguity valid at every save.
    for k, chapter in enumerate(chapters):
        if context.event_emitter is not None:
            context.event_emitter({
                "type": "chapter_progress",
                "phase": 2,
                "current": k + 1,
                "total": len(chapters),
                "name": chapter["name"],
            })
        prev_scene = doc["scenes"][-1] if doc["scenes"] else None
        payload, result = await run_structured_query(
            context,
            _build_chapter_plan_prompt(
                outline, k, prev_scene, phase1_text, inputs
            ),
            f"phase2-{run8}-c{k + 1}",
            validate=_scoped_validator(chapter["name"]),
            phase_number=2,
        )
        total_cost += float(getattr(result, "total_cost_usd", 0.0) or 0.0)
        total_turns += int(getattr(result, "num_turns", 0) or 0)
        for scene in payload["scenes"]:
            storyboard.add_scene(
                doc,
                title=scene["title"],
                narration=scene.get("narration", ""),
                action=scene["action"],
                target_hint=scene.get("target_hint", ""),
                section=chapter["name"],
            )
        storyboard.save(context.state_dir, doc)
        problems = storyboard.validate_storyboard(doc, stage="planned")
        if problems:
            raise RuntimeError(
                f"Phase 2: storyboard invalid after chapter "
                f"{chapter['name']!r}: " + "; ".join(problems)
            )
        print(
            f"  Chapter {k + 1}/{len(chapters)} {chapter['name']!r}: "
            f"{len(payload['scenes'])} scenes"
        )

    # Beat 3: the continuity pass — one no-tools read-through so the
    # chapters speak as one film.
    cont_cost, cont_turns = await _continuity_pass(
        context, doc, outline, f"phase2-{run8}-cont"
    )
    total_cost += cont_cost
    total_turns += cont_turns
    storyboard.save(context.state_dir, doc)

    artifact.write_text(storyboard.render_phase2_view(doc, inputs))
    record_phase_result(
        context, 2, result,
        cost_usd_total=total_cost, num_turns_total=total_turns,
    )
    print(summarize_run(2, artifact, result))
    print(
        f"  (storyboard: {len(doc['scenes'])} scenes in "
        f"{len(chapters)} chapters; phase total ${total_cost:.2f})"
    )
