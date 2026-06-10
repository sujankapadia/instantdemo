"""Phase 5 — Build the demo-script.json.

Translates the Phase 4 verified plan into the JSON the renderer
expects. This is mechanical: every field the renderer needs has
already been resolved by Phase 3 (source-based hypothesis) and
verified by Phase 4 (live-app probe). Phase 5 just wraps the
segments in the script envelope, normalizes field names, and
writes the file.

Tools: Read (to load Phase 4's verified plan) + Write. The agent
isn't exploring the codebase or the live app at this stage.
"""

from __future__ import annotations

import json

from .. import prompts
from ..actions import validate_segments
from ..agent_client import session_id_for_phase
from . import (
    Context,
    record_phase_result,
    run_query_on_client,
    summarize_run,
)


def _build_prompt(phase4_text: str, output_path: str) -> str:
    template = prompts.load("phase5")
    return (
        "The following is the verified plan from Phase 4 (selectors\n"
        "confirmed against the live app). Each segment has its action,\n"
        "narration, target, and pacing already resolved.\n"
        "\n"
        "---\n"
        f"{phase4_text}\n"
        "---\n"
        "\n"
        f"Write the resulting demo-script.json to: {output_path}\n"
        "\n"
        f"{template}"
    )


def _validate_script_file(artifact) -> list[str]:
    """Validate the script file end-to-end; return problems (empty = ok).

    Covers JSON well-formedness, the envelope fields, per-segment
    required fields, and the canonical action contract
    (actions.validate_segments). Collected as a list rather than
    raised so the runner can hand the full set back to the agent in
    one correction turn.
    """
    try:
        script = json.loads(artifact.read_text())
    except json.JSONDecodeError as e:
        return [f"file is not valid JSON: {e}"]

    problems: list[str] = []
    for required in ("title", "resolution", "segments"):
        if required not in script:
            problems.append(f"missing the top-level {required!r} field")
    segments = script.get("segments")
    if not isinstance(segments, list) or not segments:
        problems.append("script has no segments")
        return problems
    for i, seg in enumerate(segments, start=1):
        for required in ("action", "narration"):
            if required not in seg:
                problems.append(
                    f"segment {i} is missing the {required!r} field"
                )
    problems.extend(validate_segments(segments))
    return problems


async def run(context: Context) -> None:
    if context.client is None:
        raise RuntimeError(
            "Phase 5: no agent client provided in context. The CLI is "
            "responsible for creating and passing through a ClaudeSDKClient."
        )

    phase4 = context.phase_artifact(4)
    if not phase4.exists():
        raise RuntimeError(
            f"Phase 4 artifact missing at {phase4}. Run phase 4 first."
        )
    phase4_text = phase4.read_text()

    artifact = context.phase_artifact(5)  # demo-script.json in project root
    artifact.parent.mkdir(parents=True, exist_ok=True)

    prompt = _build_prompt(phase4_text, str(artifact))
    _agent_text, result = await run_query_on_client(
        context, prompt, session_id=session_id_for_phase(5, context.run_id)
    )

    if result is None:
        raise RuntimeError(
            "Phase 5: the Claude Agent SDK did not return a ResultMessage."
        )

    if not artifact.exists():
        raise RuntimeError(
            f"Phase 5 finished but {artifact} was not created. "
            "The agent may have written to a different path."
        )

    # Validate now rather than at render time — a contract violation
    # caught here costs seconds; caught mid-recording it costs the
    # whole take. One corrective round-trip to the agent before
    # giving up: the session still has the full context, so "fix
    # these problems" is cheap and usually sufficient.
    problems = _validate_script_file(artifact)
    if problems:
        print(
            f"\n  Script validation failed ({len(problems)} problem(s)); "
            "asking the agent to correct it...",
        )
        fix_prompt = (
            f"The demo-script.json you wrote to {artifact} failed "
            "validation:\n\n"
            + "\n".join(f"- {p}" for p in problems)
            + "\n\nRewrite the file at the same path, fixing every "
            "problem. Keep all valid segments exactly as they are. "
            "Only use the actions listed in the spec; express "
            "readiness conditions through the existing fields "
            "(e.g. goto's wait_for), never by inventing actions."
        )
        _fix_text, result = await run_query_on_client(
            context, fix_prompt,
            session_id=session_id_for_phase(5, context.run_id),
        )
        problems = _validate_script_file(artifact)
        if problems:
            raise RuntimeError(
                "Phase 5 script still invalid after one correction "
                "attempt:\n" + "\n".join(f"  - {p}" for p in problems)
            )

    script = json.loads(artifact.read_text())
    record_phase_result(context, 5, result)
    print(summarize_run(5, artifact, result))
    print(f"  ({len(script['segments'])} segments)")
