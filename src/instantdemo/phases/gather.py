"""Phase 3 — Gather technical details.

Reads the Phase 2 narrative and augments each segment with the implementation
details needed to render the demo: stable CSS selectors, wait conditions,
Playwright action types, and pacing values. The agent re-explores the
frontend source (Read / Glob / Grep) to find selectors that match the
narrative's described targets.

Output is a "complete" markdown plan — every segment from Phase 2,
plus the technical fields. Phase 4 will translate this directly to
demo-script.json without further inference.
"""

from __future__ import annotations

import asyncio

from claude_agent_sdk import ClaudeAgentOptions

from .. import prompts
from . import (
    Context,
    record_phase_result,
    run_query,
    summarize_run,
)


def _build_prompt(phase2_text: str, url: str) -> str:
    template = prompts.load("phase3")
    return (
        f"The app being demoed is running at: {url}\n"
        "\n"
        "Use this base URL for all `goto` segments. When the narrative\n"
        "references a route like `/active`, combine it with the base URL\n"
        f"to form the full URL ({url}/active). Do NOT use a different\n"
        "port from the codebase configuration — the user has chosen this\n"
        "specific URL.\n"
        "\n"
        "The following is the narrative plan from Phase 2. Each numbered\n"
        "segment is what the demo should walk through.\n"
        "\n"
        "---\n"
        f"{phase2_text}\n"
        "---\n"
        "\n"
        f"{template}"
    )


def run(context: Context) -> None:
    phase2 = context.phase_artifact(2)
    if not phase2.exists():
        raise RuntimeError(
            f"Phase 2 artifact missing at {phase2}. Run phase 2 first."
        )
    phase2_text = phase2.read_text()

    artifact = context.phase_artifact(3)
    artifact.parent.mkdir(parents=True, exist_ok=True)

    options = ClaudeAgentOptions(
        cwd=str(context.source),
        allowed_tools=["Read", "Glob", "Grep"],
        permission_mode="bypassPermissions",
    )
    prompt = _build_prompt(phase2_text, context.url)
    detailed_text, result = asyncio.run(run_query(prompt, options))

    if result is None:
        raise RuntimeError(
            "Phase 3: the Claude Agent SDK did not return a ResultMessage."
        )

    artifact.write_text(detailed_text + "\n")
    record_phase_result(context.state_dir, 3, result)
    print(summarize_run(3, artifact, result))
