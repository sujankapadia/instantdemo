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
        context, prompt, session_id=session_id_for_phase(5)
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

    # Validate the JSON now rather than at render time.
    try:
        script = json.loads(artifact.read_text())
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Phase 5 wrote {artifact} but it isn't valid JSON: {e}"
        ) from e

    # Quick schema spot-check — surfaces obvious problems before Phase 6
    # tries the drift check against a live app.
    for required in ("title", "resolution", "segments"):
        if required not in script:
            raise RuntimeError(
                f"Phase 5 produced a script missing the {required!r} field."
            )
    if not isinstance(script["segments"], list) or not script["segments"]:
        raise RuntimeError("Phase 5 produced a script with no segments.")
    for i, seg in enumerate(script["segments"], start=1):
        for required in ("action", "narration"):
            if required not in seg:
                raise RuntimeError(
                    f"Phase 5 segment {i} is missing the {required!r} field."
                )

    record_phase_result(context, 5, result)
    print(summarize_run(5, artifact, result))
    print(f"  ({len(script['segments'])} segments)")
