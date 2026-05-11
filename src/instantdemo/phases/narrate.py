"""Phase 2 — Plan the narrative.

Reads the Phase 1 artifact (analysis text + answer block) and produces
a markdown narrative plan: 4-8 segments with draft narration and
proposed actions, leading with the payoff. Pure reasoning over Phase 1
output — no tools.

Input resolution per field (highest priority wins):
  - flow:         intent.goal → phase1.md answer block → context.describe → ""
  - tone:         intent.tone → phase2.md answer block (legacy) → default "casual"
  - audience:     intent.audience → phase2.md answer block (legacy) → default "technical"
  - length:       intent.length → (none in legacy answer block) → "" (let agent pick)
  - focus:        intent.focus
  - excludes:     intent.excludes
  - addenda:      intent.addenda

The phase2.md answer-block mechanism is retained for CLI users who
prefer editing artifacts in $EDITOR. With #39 the GUI writes
intent.json, which takes priority.
"""

from __future__ import annotations

from .. import prompts
from ..agent_client import session_id_for_phase
from ..checkpoints import parse_answer_block
from . import (
    Context,
    record_phase_result,
    run_query_on_client,
    summarize_run,
)


DEFAULT_TONE = "casual"
DEFAULT_AUDIENCE = "technical"


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
        "length": (intent.length or "").strip(),
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
    length = inputs.get("length", "")
    if length:
        lines.append(f"Target length: {length}")
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


def _build_artifact(narrative_text: str, inputs: dict[str, object]) -> str:
    return (
        "<!-- ANSWER THESE BEFORE CONTINUING -->\n"
        f"tone: {inputs['tone']}\n"
        f"audience: {inputs['audience']}\n"
        f"terminology: {inputs['terminology']}\n"
        "<!-- /ANSWER -->\n"
        "\n"
        f"{narrative_text}\n"
    )


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

    narrative_text, result = await run_query_on_client(
        context, prompt, session_id=session_id_for_phase(2)
    )

    if result is None:
        raise RuntimeError(
            "Phase 2: the Claude Agent SDK did not return a ResultMessage."
        )

    artifact.write_text(_build_artifact(narrative_text, inputs))
    record_phase_result(context.state_dir, 2, result)
    print(summarize_run(2, artifact, result))
