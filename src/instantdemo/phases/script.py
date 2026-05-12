"""Phase 4 — Produce the demo-script.json.

Translates the Phase 3 technical plan into the JSON the renderer expects.
This is mechanical: every field the renderer needs has already been
resolved by Phase 3. Phase 4 just wraps the segments in the script
envelope, normalizes field names, and writes the file.

Tools: Write (and only Write — the agent shouldn't be exploring the
codebase at this stage).
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


def _build_prompt(phase3_text: str, output_path: str) -> str:
    template = prompts.load("phase4")
    return (
        "The following is the per-segment technical plan from Phase 3.\n"
        "Each segment has its action, narration, target, and pacing\n"
        "already resolved.\n"
        "\n"
        "---\n"
        f"{phase3_text}\n"
        "---\n"
        "\n"
        f"Write the resulting demo-script.json to: {output_path}\n"
        "\n"
        f"{template}"
    )


async def run(context: Context) -> None:
    if context.client is None:
        raise RuntimeError(
            "Phase 4: no agent client provided in context. The CLI is "
            "responsible for creating and passing through a ClaudeSDKClient."
        )

    phase3 = context.phase_artifact(3)
    if not phase3.exists():
        raise RuntimeError(
            f"Phase 3 artifact missing at {phase3}. Run phase 3 first."
        )
    phase3_text = phase3.read_text()

    artifact = context.phase_artifact(4)  # demo-script.json in source root
    artifact.parent.mkdir(parents=True, exist_ok=True)

    prompt = _build_prompt(phase3_text, str(artifact))
    _agent_text, result = await run_query_on_client(
        context, prompt, session_id=session_id_for_phase(4)
    )

    if result is None:
        raise RuntimeError(
            "Phase 4: the Claude Agent SDK did not return a ResultMessage."
        )

    if not artifact.exists():
        raise RuntimeError(
            f"Phase 4 finished but {artifact} was not created. "
            "The agent may have written to a different path."
        )

    # Validate the JSON now rather than at render time.
    try:
        script = json.loads(artifact.read_text())
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Phase 4 wrote {artifact} but it isn't valid JSON: {e}"
        ) from e

    # Quick schema spot-check — surfaces obvious problems before Phase 5
    # tries to validate selectors against a live app.
    for required in ("title", "resolution", "segments"):
        if required not in script:
            raise RuntimeError(
                f"Phase 4 produced a script missing the {required!r} field."
            )
    if not isinstance(script["segments"], list) or not script["segments"]:
        raise RuntimeError("Phase 4 produced a script with no segments.")
    for i, seg in enumerate(script["segments"], start=1):
        for required in ("action", "narration"):
            if required not in seg:
                raise RuntimeError(
                    f"Phase 4 segment {i} is missing the {required!r} field."
                )

    record_phase_result(context, 4, result)
    print(summarize_run(4, artifact, result))
    print(f"  ({len(script['segments'])} segments)")
