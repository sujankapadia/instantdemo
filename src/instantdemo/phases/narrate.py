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

from .. import prompts, storyboard
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


def _build_prompt(phase1_text: str, inputs: dict[str, object]) -> str:
    template = prompts.load("phase2")

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
    lines.append("")
    lines.append("---")
    lines.append("Codebase analysis (from Phase 1):")
    lines.append("")
    lines.append(phase1_text)
    lines.append("---")
    lines.append("")
    lines.append(template)

    return "\n".join(lines)


def _validate_payload(payload: dict) -> list[str]:
    """Validate the agent's plan payload before it becomes a storyboard."""
    problems: list[str] = []
    scenes = payload.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        problems.append("payload must contain a non-empty 'scenes' array")
        return problems
    if not isinstance(payload.get("title"), str) or not payload["title"]:
        problems.append("payload must contain a non-empty 'title' string")
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
        if not isinstance(scene.get("section"), str) or not scene["section"].strip():
            problems.append(
                f"scene {i}: missing 'section' (the chapter this scene "
                "belongs to)"
            )

    # Chapter coherence (M5a): each chapter is one contiguous run.
    seen_sections: list[str] = []
    for scene in scenes:
        name = scene.get("section")
        if not isinstance(name, str) or not name.strip():
            continue
        if seen_sections and seen_sections[-1] == name:
            continue
        if name in seen_sections:
            problems.append(
                f"section {name!r} reappears after another chapter began — "
                "each chapter must be one contiguous run of scenes"
            )
        seen_sections.append(name)
    if len(seen_sections) > 8:
        problems.append(
            f"{len(seen_sections)} chapters is too many — group the story "
            "into 2-6 beats"
        )
    return problems


async def run(context: Context) -> None:
    if context.client is None:
        raise RuntimeError(
            "Phase 2: no agent client provided in context. The CLI is "
            "responsible for creating and passing through a ClaudeSDKClient."
        )

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
    prompt = _build_prompt(phase1_text, inputs)

    payload, result = await run_structured_query(
        context,
        prompt,
        session_id_for_phase(2, context.run_id),
        validate=_validate_payload,
        phase_number=2,
    )

    doc = storyboard.new_document(
        title=payload["title"],
        url=context.url,
        summary=payload.get("summary", ""),
        provenance={
            "tone": inputs["tone"],
            "audience": inputs["audience"],
            "terminology": inputs["terminology"],
            "intent_goal": inputs["flow"],
        },
    )
    for scene in payload["scenes"]:
        storyboard.add_scene(
            doc,
            title=scene["title"],
            narration=scene.get("narration", ""),
            action=scene["action"],
            target_hint=scene.get("target_hint", ""),
            section=scene.get("section"),
        )
    storyboard.save(context.state_dir, doc)

    artifact.write_text(storyboard.render_phase2_view(doc, inputs))
    record_phase_result(context, 2, result)
    print(summarize_run(2, artifact, result))
    print(f"  (storyboard: {len(doc['scenes'])} scenes)")
