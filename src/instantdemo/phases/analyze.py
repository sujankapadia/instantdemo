"""Phase 1 — Understand the product.

Runs the codebase-analysis prompt through the Claude Agent SDK with
read-only filesystem tools (Read, Glob, Grep). Streams the agent's
prose to stdout while the run is in progress, then writes the final
text to `.instantdemo/phase1.md` with an answer block at the top for
the user to fill in before Phase 2 begins.

This mirrors the pattern validated in `instantdemo-sdk-spike/spike.py`.
"""

from __future__ import annotations

import asyncio

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    query,
)

from .. import prompts, state
from . import Context


def _build_prompt(context: Context) -> str:
    template = prompts.load("phase1")
    if context.describe:
        return f"The user wants to demo: {context.describe}\n\n{template}"
    return template


async def _run_query(prompt: str, source: str) -> tuple[str, ResultMessage | None]:
    """Run the SDK query and return (agent_text, result_message)."""
    options = ClaudeAgentOptions(
        cwd=source,
        allowed_tools=["Read", "Glob", "Grep"],
        permission_mode="bypassPermissions",
    )
    text_chunks: list[str] = []
    result: ResultMessage | None = None
    async for msg in query(prompt=prompt, options=options):
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    print(block.text, flush=True)
                    text_chunks.append(block.text)
        elif isinstance(msg, ResultMessage):
            result = msg
    return "\n".join(text_chunks), result


def _build_artifact(agent_text: str, context: Context) -> str:
    """Wrap the agent's prose with the answer block the user fills in."""
    flow = context.describe or ""
    return (
        "<!-- ANSWER THESE BEFORE CONTINUING -->\n"
        f"flow: {flow}\n"
        f"url: {context.url}\n"
        "seed_data_ready: \n"
        "<!-- /ANSWER -->\n"
        "\n"
        f"{agent_text}\n"
    )


def _record_metrics(state_dir, result: ResultMessage) -> None:
    """Stash phase metrics into state.json's phase entry.

    Full metrics.jsonl logging arrives in Task #15; for now we
    surface cost/duration/turns inline so users can sanity-check.
    """
    s = state.load(state_dir)
    entry = s.setdefault("phases", {}).setdefault("1", {})
    entry["cost_usd"] = result.total_cost_usd
    entry["duration_ms"] = result.duration_ms
    entry["duration_api_ms"] = result.duration_api_ms
    entry["num_turns"] = result.num_turns
    entry["session_id_phase"] = result.session_id
    state.save(state_dir, s)


def run(context: Context) -> None:
    artifact = context.phase_artifact(1)
    artifact.parent.mkdir(parents=True, exist_ok=True)

    prompt = _build_prompt(context)
    agent_text, result = asyncio.run(_run_query(prompt, str(context.source)))

    if result is None:
        raise RuntimeError(
            "Phase 1: the Claude Agent SDK did not return a ResultMessage. "
            "The run may have been interrupted or the SDK API has changed."
        )

    artifact.write_text(_build_artifact(agent_text, context))
    _record_metrics(context.state_dir, result)

    print(
        f"\nPhase 1 done — {artifact} "
        f"(${result.total_cost_usd:.2f}, {result.duration_ms / 1000:.1f}s, "
        f"{result.num_turns} turns)"
    )
