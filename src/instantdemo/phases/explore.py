"""Phase 4 — Explore the live application.

Reads the Phase 3 hypothesis plan and verifies each segment's
selectors against the running app via Playwright probes. Writes a
verified plan to `.instantdemo/phase4.md` that Phase 5 (Build)
consumes instead of the raw Phase 3 hypothesis.

Tools: Read (for phase3.md and the occasional source consult) and
Bash (for curl and a Playwright probe via python heredoc). No
Write — the agent doesn't produce JSON at this stage; the runner
saves the agent's response text to phase4.md.
"""

from __future__ import annotations

from .. import prompts
from ..agent_client import session_id_for_phase
from . import (
    Context,
    record_phase_result,
    run_query_on_client,
    summarize_run,
)


def _build_prompt(phase3_text: str, url: str, phase3_path: str) -> str:
    template = prompts.load("phase4")
    return (
        f"The app being demoed is running at: {url}\n"
        f"The Phase 3 plan is at: {phase3_path}\n"
        "\n"
        "The following is the Phase 3 hypothesis plan. Each segment\n"
        "has a primary selector derived from source code and (often)\n"
        "fallback selectors in its Notes line.\n"
        "\n"
        "---\n"
        f"{phase3_text}\n"
        "---\n"
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

    artifact = context.phase_artifact(4)
    artifact.parent.mkdir(parents=True, exist_ok=True)

    prompt = _build_prompt(phase3_text, context.url, str(phase3))
    verified_text, result = await run_query_on_client(
        context, prompt, session_id=session_id_for_phase(4)
    )

    if result is None:
        raise RuntimeError(
            "Phase 4: the Claude Agent SDK did not return a ResultMessage."
        )

    artifact.write_text(verified_text + "\n")
    record_phase_result(context, 4, result)
    print(summarize_run(4, artifact, result))
