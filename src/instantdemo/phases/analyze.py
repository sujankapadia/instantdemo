"""Phase 1 — Understand the product.

Runs the codebase-analysis prompt through the shared ClaudeSDKClient
with read-only filesystem tools (Read, Glob, Grep). Streams the agent's
prose to stdout while the run is in progress, then writes the final
text to `.instantdemo/phase1.md` with an answer block at the top for
the user to fill in before Phase 2 begins.
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


def _build_prompt(context: Context) -> str:
    """Compose Phase 1's prompt from the structured intent plus the
    static template. Falls back to `describe` for legacy callers
    (Context with an empty Intent + a populated describe field)."""
    template = prompts.load("phase1")
    intent = context.intent
    goal = intent.goal or context.describe or ""

    prefix_lines: list[str] = []
    if goal:
        prefix_lines.append(f"The user wants to demo: {goal}")
    if intent.focus:
        prefix_lines.append(
            "Focus on: " + "; ".join(intent.focus)
        )
    if intent.excludes:
        prefix_lines.append(
            "Exclude: " + "; ".join(intent.excludes)
        )

    if not prefix_lines:
        return template
    return "\n".join(prefix_lines) + "\n\n" + template


def _build_artifact(agent_text: str, context: Context) -> str:
    """Wrap the agent's prose with the answer block the user fills in."""
    flow = context.intent.goal or context.describe or ""
    return (
        "<!-- ANSWER THESE BEFORE CONTINUING -->\n"
        f"flow: {flow}\n"
        f"url: {context.url}\n"
        "seed_data_ready: \n"
        "<!-- /ANSWER -->\n"
        "\n"
        f"{agent_text}\n"
    )


async def run(context: Context) -> None:
    if context.client is None:
        raise RuntimeError(
            "Phase 1: no agent client provided in context. The CLI is "
            "responsible for creating and passing through a ClaudeSDKClient."
        )

    artifact = context.phase_artifact(1)
    artifact.parent.mkdir(parents=True, exist_ok=True)

    prompt = _build_prompt(context)
    agent_text, result = await run_query_on_client(
        context, prompt, session_id=session_id_for_phase(1, context.run_id)
    )

    if result is None:
        raise RuntimeError(
            "Phase 1: the Claude Agent SDK did not return a ResultMessage. "
            "The run may have been interrupted or the SDK API has changed."
        )

    artifact.write_text(_build_artifact(agent_text, context))
    record_phase_result(context, 1, result)
    print(summarize_run(1, artifact, result))
