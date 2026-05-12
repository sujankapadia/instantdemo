"""Phase 5 — Validate the script against the live app, then render.

Two halves:

1. **AI validation**. The agent reads demo-script.json, curls each
   `goto` URL, and runs a Playwright probe to confirm selectors
   resolve. It writes a markdown report to `.instantdemo/phase5.md`
   ending with one of:

       RENDER_OK
       RENDER_BLOCKED: <reason>

2. **Render**. If the directive is `RENDER_OK`, the runner invokes
   the bundled renderer (`instantdemo.render.main`) directly in-process
   to produce the final MP4. `RENDER_BLOCKED` aborts before render.

Tools for validation: `Read` (for demo-script.json) and Bash with
`curl` and `python` (for the Playwright probe). The agent doesn't get
Write — it can use `python -c` or `python <<EOF` heredocs for the
probe.
"""

from __future__ import annotations

import asyncio
import re

from .. import prompts
from ..agent_client import session_id_for_phase
from ..render import main as render_main
from . import (
    Context,
    record_phase_result,
    run_query_on_client,
    summarize_run,
)


DIRECTIVE_RE = re.compile(
    r"^\s*(?P<directive>RENDER_OK|RENDER_BLOCKED)(?:\s*:\s*(?P<reason>.+))?\s*$",
    re.MULTILINE,
)


def _build_prompt(context: Context) -> str:
    template = prompts.load("phase5")
    return (
        f"The app is running at: {context.url}\n"
        f"The demo script is at: {context.script_path}\n"
        "\n"
        f"{template}"
    )


def _parse_directive(report: str) -> tuple[str, str | None]:
    """Pull the last RENDER_OK / RENDER_BLOCKED directive from the report.

    Returns (directive, reason). `reason` is None for RENDER_OK.
    Raises RuntimeError if no directive is found — the agent didn't
    follow the prompt.
    """
    matches = list(DIRECTIVE_RE.finditer(report))
    if not matches:
        raise RuntimeError(
            "Phase 5 finished but the validation report has no "
            "RENDER_OK / RENDER_BLOCKED directive. The agent didn't "
            "follow the prompt — re-running Phase 5 will likely help."
        )
    last = matches[-1]
    return last.group("directive"), last.group("reason")


async def _run_validation(context: Context) -> tuple[str, "object | None"]:
    """Run the agent validation pass. Returns (report_text, ResultMessage)."""
    if context.client is None:
        raise RuntimeError(
            "Phase 5: no agent client provided in context. The CLI is "
            "responsible for creating and passing through a ClaudeSDKClient."
        )
    prompt = _build_prompt(context)
    return await run_query_on_client(
        context, prompt, session_id=session_id_for_phase(5)
    )


def _invoke_renderer(context: Context) -> None:
    """Call the bundled renderer in-process with the user's chosen TTS."""
    argv = [
        str(context.script_path),
        "--tts",
        context.tts,
        "-o",
        str(context.output),
    ]
    print(f"\n[Phase 5] Validation passed — running renderer:")
    print(f"           instantdemo render {' '.join(argv)}\n")
    render_main(argv)


async def run(context: Context) -> None:
    if not context.script_path.exists():
        raise RuntimeError(
            f"Demo script missing at {context.script_path}. Run phase 4 first."
        )

    artifact = context.phase_artifact(5)
    artifact.parent.mkdir(parents=True, exist_ok=True)

    report_text, result = await _run_validation(context)

    if result is None:
        raise RuntimeError(
            "Phase 5: the Claude Agent SDK did not return a ResultMessage."
        )

    artifact.write_text(report_text + "\n")
    record_phase_result(context, 5, result)
    print(summarize_run(5, artifact, result))

    directive, reason = _parse_directive(report_text)
    if directive == "RENDER_BLOCKED":
        raise RuntimeError(
            f"Phase 5 blocked the render. Reason: {reason or '(none given)'}\n"
            f"See {artifact} for the full report."
        )

    # RENDER_OK — proceed. The renderer uses `sync_playwright()`,
    # which refuses to start a browser from inside a running asyncio
    # loop (the GUI's case under uvicorn). Offload to the default
    # executor so the sync call runs in a worker thread without an
    # active loop. The CLI path also passes through here, where the
    # current loop is the one driving `asyncio.run(...)` — same
    # offload pattern is safe there too. See issue #33.
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _invoke_renderer, context)
