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
from ..render import render_section_main
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


def _section_render_plan(context: Context) -> tuple[int, int, int] | None:
    """Decide whether a scoped chapter render is possible (M5b):
    returns (start_idx, end_idx, old_chapter_len) — 0-based segment
    span in the NEW script plus the chapter's length in the OLD
    timing — or None to fall back to a full record.

    Requirements: an existing film + timing with recorded durations;
    the storyboard's scoped chapter projecting onto a contiguous
    script span; prefix/tail counts consistent between old timing
    and the new script (out-of-scope scenes are untouched by a
    scoped re-plan, so their counts must match — anything else means
    the project drifted and a full record is the safe path)."""
    import json

    from instantdemo import storyboard

    section = context.section_scope
    if not section:
        return None
    timing_path = context.state_dir / "segment-timing.json"
    if not (context.output.exists() and timing_path.exists()):
        print("[Phase 6] Scoped render unavailable (no film/timing) — full record")
        return None
    try:
        doc = storyboard.load(context.state_dir)
    except RuntimeError:
        return None
    flags = [s.get("section") == section for s in doc.get("scenes", [])]
    if not any(flags):
        print(f"[Phase 6] No chapter {section!r} — full record")
        return None
    start_idx = flags.index(True)
    chapter_len = sum(flags)
    if any(flags[start_idx + chapter_len :]):
        print("[Phase 6] Chapter not contiguous — full record")
        return None
    script = json.loads(context.script_path.read_text())
    n_new = len(script.get("segments") or [])
    if n_new != len(flags):
        print("[Phase 6] Script/storyboard counts diverge — full record")
        return None
    old_rows = (
        json.loads(timing_path.read_text()).get("segments") or []
    )
    tail_len = n_new - start_idx - chapter_len
    old_chapter_len = len(old_rows) - start_idx - tail_len
    if old_chapter_len < 1 or any(
        "recorded_clean_duration_s" not in r
        for r in old_rows[:start_idx]
    ):
        print("[Phase 6] Old timing unusable for splice — full record")
        return None
    return start_idx, start_idx + chapter_len - 1, old_chapter_len


def _progress_emitter(loop, emit):
    """Thread-safe render progress (M8/#85): the renderer runs in an
    executor thread, and the SSE queue's put_nowait is NOT thread-safe
    from there — marshal each event onto the loop with
    call_soon_threadsafe. Returns None when there's no emitter (CLI)."""
    if emit is None:
        return None

    def on_progress(stage: str, current: int, total: int) -> None:
        loop.call_soon_threadsafe(emit, {
            "type": "render_progress",
            "phase": 6,
            "stage": stage,
            "current": current,
            "total": total,
        })

    return on_progress


def _invoke_renderer(context: Context, on_progress=None) -> None:
    """Call the bundled renderer in-process. The project's tts.json
    carries the voice (provider/stock voice/cloned reference/
    pronunciations); an explicit Context.tts (CLI --tts) overrides
    the config's provider. A scoped chapter revision (M5b) records
    and splices only the chapter when the project's film/timing
    allow it. `on_progress(stage, current, total)` (M8) reports
    per-segment narrating/recording progress; None in the CLI."""
    plan = _section_render_plan(context)
    if plan is not None:
        start_idx, end_idx, old_chapter_len = plan
        print(
            f"\n[Phase 6] Drift check passed — scoped render of "
            f"chapter {context.section_scope!r} "
            f"(segments {start_idx}..{end_idx})\n"
        )
        render_section_main(
            context.script_path,
            context.output,
            context.state_dir,
            start_idx,
            end_idx,
            old_chapter_len,
            tts_config_path=context.project / "tts.json",
            tts_override=context.tts,
            on_progress=on_progress,
        )
        return
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
    render_main(argv, on_progress=on_progress)


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
                n = takes.snapshot_unless_current(
                    context.project, "edited cut"
                )
                if n is not None:
                    print(f"[Phase 6] Kept your current film as version {n}")
        except OSError as exc:
            print(f"[Phase 6] WARNING: pre-render take failed: {exc}")
        on_progress = _progress_emitter(loop, context.event_emitter)
        await loop.run_in_executor(
            None, _invoke_renderer, context, on_progress
        )
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
