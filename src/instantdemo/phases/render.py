"""Phase 6 — Drift check the script against the live app, then render.

Two halves:

1. **AI drift check**. The agent reads demo-script.json, curls each
   distinct `goto` URL, and runs a small Playwright smoke check that
   the first interactive step resolves. It writes a markdown report
   to `.instantdemo/phase6.md` ending with one of:

       RENDER_OK
       RENDER_BLOCKED: <reason>

   Selector verification already happened upstream in Phase 4
   (Explore). The drift check exists to catch the case where the
   app's state changed between Explore and Render (restart, data
   wipe, manual script edit, etc.).

2. **Render**. If the directive is `RENDER_OK`, the runner invokes
   the bundled renderer (`instantdemo.render.main`) directly in-process
   to produce the final MP4. `RENDER_BLOCKED` aborts before render.

Tools for the drift check: `Read` (for demo-script.json) and Bash
with `curl` and `python` (for the Playwright smoke probe). The agent
doesn't get Write — it can use `python -c` or `python <<EOF` heredocs
for the probe.
"""

from __future__ import annotations

import asyncio
import re
import time

from .. import prompts, takes
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
    template = prompts.load("phase6")
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
            "Phase 6 finished but the report has no RENDER_OK / "
            "RENDER_BLOCKED directive. The agent didn't follow the "
            "prompt — re-running Phase 6 will likely help."
        )
    last = matches[-1]
    return last.group("directive"), last.group("reason")


async def _run_drift_check(context: Context) -> tuple[str, "object | None"]:
    """Run the agent drift check. Returns (report_text, ResultMessage)."""
    if context.client is None:
        raise RuntimeError(
            "Phase 6: no agent client provided in context. The CLI is "
            "responsible for creating and passing through a ClaudeSDKClient."
        )
    prompt = _build_prompt(context)
    return await run_query_on_client(
        context, prompt, session_id=session_id_for_phase(6, context.run_id)
    )


def _invoke_renderer(context: Context) -> None:
    """Call the bundled renderer in-process. The project's tts.json
    carries the voice (provider/stock voice/cloned reference/
    pronunciations); an explicit Context.tts (CLI --tts) overrides
    the config's provider."""
    argv = [
        str(context.script_path),
        "--tts-config",
        str(context.project / "tts.json"),
        "-o",
        str(context.output),
    ]
    if context.tts is not None:
        argv += ["--tts", context.tts]
    print(f"\n[Phase 6] Drift check passed — running renderer:")
    print(f"           instantdemo render {' '.join(argv)}\n")
    render_main(argv)


async def run(context: Context) -> None:
    if not context.script_path.exists():
        raise RuntimeError(
            f"Demo script missing at {context.script_path}. Run phase 5 first."
        )

    artifact = context.phase_artifact(6)
    artifact.parent.mkdir(parents=True, exist_ok=True)

    # Track the true phase wall-clock — drift check + (when not BLOCKED)
    # the executor that runs the renderer. See issue #55: the SDK's
    # `result.duration_ms` only covers the agent query.
    phase_start = time.monotonic()

    report_text, result = await _run_drift_check(context)

    if result is None:
        raise RuntimeError(
            "Phase 6: the Claude Agent SDK did not return a ResultMessage."
        )

    artifact.write_text(report_text + "\n")

    directive, reason = _parse_directive(report_text)

    if directive == "RENDER_BLOCKED":
        # The drift check is the whole phase here — no executor.
        phase_duration_ms = int((time.monotonic() - phase_start) * 1000)
        record_phase_result(context, 6, result, duration_ms=phase_duration_ms)
        print(summarize_run(6, artifact, result, duration_ms=phase_duration_ms))
        raise RuntimeError(
            f"Phase 6 blocked the render. Reason: {reason or '(none given)'}\n"
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
    try:
        # Before overwriting an existing film, make sure its CURRENT
        # state is a take (M5a). Renders snapshot AFTER rendering and
        # revisions BEFORE mutating — so a film edited since its
        # render exists in no take, and a regenerate would destroy it
        # despite the gated-regenerate copy's promise. Skipped when
        # the newest take already IS the current film (is_current).
        try:
            if context.output.exists():
                listing = takes.list_takes(context.project)
                if not (listing and listing[0].get("is_current")):
                    n = takes.snapshot(context.project, label="edited cut")
                    print(f"[Phase 6] Kept your current film as version {n}")
        except OSError as exc:
            print(f"[Phase 6] WARNING: pre-render take failed: {exc}")
        await loop.run_in_executor(None, _invoke_renderer, context)
        # Versioned take after every successful render (M4): the
        # film just made becomes restorable history. A snapshot
        # failure must never fail the phase.
        try:
            n = takes.snapshot(context.project, label="render")
            print(f"[Phase 6] Saved as version {n}")
        except OSError as exc:
            print(f"[Phase 6] WARNING: take snapshot failed: {exc}")
    finally:
        # Record AFTER the executor so duration_ms reflects the true
        # phase wall-clock. The try/finally guarantees we still record
        # if the renderer raises (e.g. ffmpeg failure, Playwright
        # crash) so the failed phase's metrics are preserved.
        phase_duration_ms = int((time.monotonic() - phase_start) * 1000)
        record_phase_result(context, 6, result, duration_ms=phase_duration_ms)
        print(summarize_run(6, artifact, result, duration_ms=phase_duration_ms))
