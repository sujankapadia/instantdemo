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

from claude_agent_sdk import ClaudeAgentOptions

from .. import prompts
from ..render import main as render_main
from . import (
    Context,
    record_phase_result,
    run_query,
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


def _run_validation(context: Context) -> tuple[str, "object | None"]:
    """Run the agent validation pass. Returns (report_text, ResultMessage)."""
    options = ClaudeAgentOptions(
        cwd=str(context.source),
        allowed_tools=["Read", "Bash"],
        permission_mode="bypassPermissions",
    )
    prompt = _build_prompt(context)
    return asyncio.run(run_query(prompt, options))


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


def run(context: Context) -> None:
    if not context.script_path.exists():
        raise RuntimeError(
            f"Demo script missing at {context.script_path}. Run phase 4 first."
        )

    artifact = context.phase_artifact(5)
    artifact.parent.mkdir(parents=True, exist_ok=True)

    report_text, result = _run_validation(context)

    if result is None:
        raise RuntimeError(
            "Phase 5: the Claude Agent SDK did not return a ResultMessage."
        )

    artifact.write_text(report_text + "\n")
    record_phase_result(context.state_dir, 5, result)
    print(summarize_run(5, artifact, result))

    directive, reason = _parse_directive(report_text)
    if directive == "RENDER_BLOCKED":
        raise RuntimeError(
            f"Phase 5 blocked the render. Reason: {reason or '(none given)'}\n"
            f"See {artifact} for the full report."
        )

    # RENDER_OK — proceed.
    _invoke_renderer(context)
