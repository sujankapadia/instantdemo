"""Phase 2 — Plan the narrative.

Reads the Phase 1 artifact (analysis text + answer block) and produces
a markdown narrative plan: 4-8 segments with draft narration and
proposed actions, leading with the payoff. Pure reasoning over Phase 1
output — no tools.

Inputs come from three places, in priority order for each field:
  - flow:         phase1.md answer block → context.describe → "(let agent pick)"
  - tone:         phase2.md answer block (re-run) → default "casual"
  - audience:     phase2.md answer block (re-run) → default "technical"
  - terminology:  phase2.md answer block (re-run) → default ""

The runner-prepended answer block at the top of phase2.md only
takes effect on a re-run (`--from-phase 2` after editing the values).
For the first run we use defaults.
"""

from __future__ import annotations

import asyncio

from claude_agent_sdk import ClaudeAgentOptions

from .. import prompts
from ..checkpoints import parse_answer_block
from . import (
    Context,
    record_phase_result,
    run_query,
    summarize_run,
)


DEFAULT_TONE = "casual"
DEFAULT_AUDIENCE = "technical"


def _resolve_inputs(
    context: Context, phase1_answers: dict[str, str], phase2_answers: dict[str, str]
) -> dict[str, str]:
    return {
        "flow": (phase1_answers.get("flow") or context.describe or "").strip(),
        "tone": (phase2_answers.get("tone") or DEFAULT_TONE).strip(),
        "audience": (phase2_answers.get("audience") or DEFAULT_AUDIENCE).strip(),
        "terminology": (phase2_answers.get("terminology") or "").strip(),
    }


def _build_prompt(phase1_text: str, inputs: dict[str, str]) -> str:
    template = prompts.load("phase2")

    lines: list[str] = []
    if inputs["flow"]:
        lines.append(f"The user wants to demo: {inputs['flow']}")
        lines.append("")
    lines.append(f"Tone: {inputs['tone']}")
    lines.append(f"Audience: {inputs['audience']}")
    if inputs["terminology"]:
        lines.append(f"Terminology to use: {inputs['terminology']}")
    lines.append("")
    lines.append("---")
    lines.append("Codebase analysis (from Phase 1):")
    lines.append("")
    lines.append(phase1_text)
    lines.append("---")
    lines.append("")
    lines.append(template)

    return "\n".join(lines)


def _build_artifact(narrative_text: str, inputs: dict[str, str]) -> str:
    return (
        "<!-- ANSWER THESE BEFORE CONTINUING -->\n"
        f"tone: {inputs['tone']}\n"
        f"audience: {inputs['audience']}\n"
        f"terminology: {inputs['terminology']}\n"
        "<!-- /ANSWER -->\n"
        "\n"
        f"{narrative_text}\n"
    )


def run(context: Context) -> None:
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

    options = ClaudeAgentOptions(
        cwd=str(context.source),
        allowed_tools=[],  # Pure reasoning — no filesystem access needed.
        permission_mode="bypassPermissions",
    )
    narrative_text, result = asyncio.run(run_query(prompt, options))

    if result is None:
        raise RuntimeError(
            "Phase 2: the Claude Agent SDK did not return a ResultMessage."
        )

    artifact.write_text(_build_artifact(narrative_text, inputs))
    record_phase_result(context.state_dir, 2, result)
    print(summarize_run(2, artifact, result))
