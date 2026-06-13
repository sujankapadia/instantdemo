"""Phase 1 — Understand the product, explore-first (M1).

The live app is the primary evidence: the agent drives it with
headless Playwright via Bash, saving a screenshot per visited screen
to `.instantdemo/exploration/` (streamed to the GUI as `screenshot`
SSE events by a concurrent watcher task). When a source directory is
present it MAY also be read (hidden routes, terminology) — jailed
file tools, live app wins conflicts. An optional product one-pager
(`product-context.md` in the project root) is injected with the
trust rule proven in the §5 bake-off experiments.

The agent ends with a fenced JSON payload (app model + PROPOSED
intent + screens + warnings), validated via the shared
run_structured_query pattern. The runner records the proposal to
state.json (`intent_proposal`, the `explore_findings` precedent) for
the GUI's confirmation card, and renders phase1.md as a view — with
the ANSWER block preserved so narrate.py's fallback chain and the
CLI flow keep working.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

from .. import prompts
from .. import state as state_mod
from ..agent_client import session_id_for_phase
from . import (
    Context,
    record_phase_result,
    run_structured_query,
    summarize_run,
)

EXPLORATION_DIRNAME = "exploration"
DOCS_FILENAME = "product-context.md"
DOCS_MAX_CHARS = 10_000
SCREENSHOT_RE = re.compile(r"^[A-Za-z0-9._-]+\.png$")

_DOCS_SECTION = """\
The user has provided product documentation for this app (e.g. a
README or product one-pager). Use it for framing and vocabulary —
what the product is called, what its features are named, who it's
for. The documentation may be stale or describe a different
deployment: where it conflicts with what you observe in the live
app, TRUST THE LIVE APP and record the discrepancy in `warnings`.

<product-documentation>
{docs}
</product-documentation>
"""

_SOURCE_SECTION = """\
The app's source code is available at: {source}
You MAY use Read/Glob/Grep there to discover hidden routes, exact
feature names, and terminology — but the live app is the primary
evidence; verify anything source-derived against the running app
before reporting it.
"""


def exploration_dir(state_dir: Path) -> Path:
    return state_dir / EXPLORATION_DIRNAME


def _load_docs(project: Path) -> str | None:
    path = project / DOCS_FILENAME
    if not path.exists():
        return None
    text = path.read_text().strip()
    if not text:
        return None
    return text[:DOCS_MAX_CHARS]


def _build_prompt(context: Context, exp_dir: Path) -> str:
    template = prompts.load("phase1")
    # str.replace, NOT str.format — the template is full of JSON braces.
    body = template.replace("{url}", context.url).replace(
        "{exploration_dir}", str(exp_dir)
    )

    prefix_lines: list[str] = []
    intent = context.intent
    goal = (intent.goal or context.describe or "").strip()
    if goal:
        prefix_lines.append(f"The user wants to demo: {goal}")
    if intent.focus:
        prefix_lines.append("Focus on: " + "; ".join(intent.focus))
    if intent.excludes:
        prefix_lines.append("Exclude: " + "; ".join(intent.excludes))

    sections: list[str] = []
    if prefix_lines:
        sections.append("\n".join(prefix_lines))

    docs = _load_docs(context.project)
    if docs:
        sections.append(_DOCS_SECTION.format(docs=docs))

    # A real source dir was supplied when source differs from the
    # project dir (the CLI colocates them; the GUI passes source
    # explicitly or falls back to project — see runs.py).
    if context.source != context.project:
        sections.append(_SOURCE_SECTION.format(source=context.source))

    sections.append(body)
    return "\n\n".join(sections)


def _make_validator(exp_dir: Path):
    """Validator closure bound to the exploration dir: payload rules
    plus the screenshots-exist requirement (checked on DISK — the
    corrective retry turn is the enforcement mechanism when the agent
    explored without saving any PNGs)."""

    def _validate(payload: dict) -> list[str]:
        return _validate_payload(payload, exp_dir)

    return _validate


def _validate_payload(payload: dict, exp_dir: Path | None = None) -> list[str]:
    problems: list[str] = []
    app_model = payload.get("app_model")
    if not isinstance(app_model, str) or not app_model.strip():
        problems.append("'app_model' must be a non-empty string")

    proposal = payload.get("proposed_intent")
    if not isinstance(proposal, dict):
        problems.append("'proposed_intent' must be an object")
    else:
        if not isinstance(proposal.get("goal"), str) or not proposal["goal"].strip():
            problems.append("'proposed_intent.goal' must be a non-empty string")
        for field in ("audience", "tone"):
            value = proposal.get(field)
            if value is not None and not isinstance(value, str):
                problems.append(
                    f"'proposed_intent.{field}' must be a string or null"
                )
        for field in ("focus", "excludes", "addenda"):
            value = proposal.get(field)
            if value is not None and (
                not isinstance(value, list)
                or any(not isinstance(v, str) for v in value)
            ):
                problems.append(
                    f"'proposed_intent.{field}' must be a list of strings"
                )

    screens = payload.get("screens")
    if screens is not None:
        if not isinstance(screens, list):
            problems.append("'screens' must be a list")
        else:
            for i, screen in enumerate(screens, start=1):
                if not isinstance(screen, dict) or not screen.get("name"):
                    problems.append(f"screens[{i}]: must have a 'name'")
                    continue
                shot = screen.get("screenshot")
                if shot is not None and not SCREENSHOT_RE.match(str(shot)):
                    problems.append(
                        f"screens[{i}]: screenshot {shot!r} must be a bare "
                        "filename like 002-notes-list.png"
                    )

    warnings = payload.get("warnings")
    if warnings is not None and (
        not isinstance(warnings, list)
        or any(not isinstance(w, str) for w in warnings)
    ):
        problems.append("'warnings' must be a list of strings")

    # Screenshots are part of the contract (they feed the GUI
    # filmstrip and the intent-confirmation card): at least one
    # visited screen must reference a PNG that actually exists in
    # the exploration dir, and every reference must resolve.
    if exp_dir is not None and isinstance(screens, list) and screens:
        existing: set[str] = set()
        if exp_dir.is_dir():
            existing = {p.name for p in exp_dir.glob("*.png")}
        referenced = [
            str(s.get("screenshot"))
            for s in screens
            if isinstance(s, dict) and s.get("screenshot")
        ]
        missing = [r for r in referenced if r not in existing]
        if missing:
            problems.append(
                "screenshots referenced but not found in "
                f"{exp_dir}: {', '.join(missing)} — save them with "
                "page.screenshot(path=...) before re-emitting"
            )
        if not any(r in existing for r in referenced):
            problems.append(
                "no screenshots were saved: capture a PNG per visited "
                f"screen into {exp_dir} (page.screenshot) and reference "
                "the filenames in screens[].screenshot, then re-emit "
                "the JSON"
            )
    return problems


def _normalized_proposal(payload: dict) -> dict[str, Any]:
    """Proposal shaped exactly like the Intent dataclass (missing
    list fields become empty lists) so the GUI can render it in
    IntentEditor without massaging."""
    proposal = payload["proposed_intent"]
    return {
        "goal": proposal.get("goal", "").strip(),
        "audience": proposal.get("audience"),
        "tone": proposal.get("tone"),
        "focus": list(proposal.get("focus") or []),
        "excludes": list(proposal.get("excludes") or []),
        "addenda": list(proposal.get("addenda") or []),
    }


def _render_view(payload: dict, context: Context) -> str:
    proposal = _normalized_proposal(payload)
    flow = (
        context.intent.goal
        or context.describe
        or proposal["goal"]
    ).strip()
    lines = [
        "<!-- ANSWER THESE BEFORE CONTINUING -->",
        f"flow: {flow}",
        f"url: {context.url}",
        "seed_data_ready: ",
        "<!-- /ANSWER -->",
        "",
        payload["app_model"].strip(),
    ]
    screens = payload.get("screens") or []
    if screens:
        lines += ["", "## Screens"]
        for screen in screens:
            entry = f"- **{screen.get('name', '?')}**"
            if screen.get("route"):
                entry += f" (`{screen['route']}`)"
            if screen.get("notes"):
                entry += f" — {screen['notes']}"
            if screen.get("screenshot"):
                entry += f" [screenshot: {screen['screenshot']}]"
            lines.append(entry)
    lines += ["", "## Proposed demo intent", "", f"- **Goal:** {proposal['goal']}"]
    for label, key in (
        ("Audience", "audience"), ("Tone", "tone"),
    ):
        if proposal.get(key):
            lines.append(f"- **{label}:** {proposal[key]}")
    for label, key in (
        ("Focus", "focus"), ("Exclude", "excludes"), ("Guidance", "addenda"),
    ):
        if proposal.get(key):
            lines.append(f"- **{label}:** " + "; ".join(proposal[key]))
    warnings = payload.get("warnings") or []
    if warnings:
        lines += ["", "## Warnings"]
        lines += [f"- {w}" for w in warnings]
    return "\n".join(lines) + "\n"


def new_screenshots(directory: Path, seen: set[str]) -> list[str]:
    """Pure diff helper: PNG filenames in `directory` not yet in
    `seen`, sorted; adds them to `seen`."""
    if not directory.is_dir():
        return []
    fresh = sorted(
        p.name
        for p in directory.iterdir()
        if p.is_file() and SCREENSHOT_RE.match(p.name) and p.name not in seen
    )
    seen.update(fresh)
    return fresh


async def watch_screenshots(
    directory: Path,
    emit,
    seen: set[str],
    *,
    phase: int,
    url_prefix: str,
    interval: float = 1.0,
) -> None:
    """Poll a screenshot dir while an agent works, emitting one
    `screenshot` SSE event per new PNG. Cancelled by the runner when
    the query completes (a final scan catches stragglers). Shared by
    Phase 1 (exploration shots) and Phase 4 (rehearsal shots)."""
    while True:
        for name in new_screenshots(directory, seen):
            emit(screenshot_event(name, phase=phase, url_prefix=url_prefix))
        await asyncio.sleep(interval)


def screenshot_event(name: str, *, phase: int, url_prefix: str) -> dict[str, Any]:
    return {
        "type": "screenshot",
        "phase": phase,
        "file": name,
        "url": f"{url_prefix}/{name}",
    }


_PROGRESS_SETUP_RE = re.compile(r"^setup\s+(\d+)\s*/\s*(\d+)\s*$")
_PROGRESS_SCENE_RE = re.compile(r"^scene\s+(s\d+)\s*$")


def parse_progress_line(line: str) -> dict[str, Any] | None:
    """One line of the rehearsal script's progress.log (M8/#85):
    `setup k/N` during the verified-setup prefix replay, `scene s<id>`
    per in-scope scene. Anything else → None (the agent's formatting
    is probabilistic; tolerance is the contract)."""
    line = line.strip()
    m = _PROGRESS_SETUP_RE.match(line)
    if m:
        current, total = int(m.group(1)), int(m.group(2))
        if total <= 0 or current <= 0:
            return None
        return {"kind": "setup", "current": current, "total": total}
    m = _PROGRESS_SCENE_RE.match(line)
    if m:
        return {"kind": "scene", "scene_id": m.group(1)}
    return None


async def tail_progress_log(
    path: Path,
    emit,
    *,
    phase: int = 4,
    interval: float = 0.5,
) -> None:
    """Tail the rehearsal progress.log (M8/#85): the agent's Bash
    stdout is invisible to the runner, so the script appends progress
    lines to a file and this coroutine polls it — the same filesystem
    pattern as watch_screenshots. The file may never appear (the
    contract is tolerant); truncation resets the offset; partial
    lines are buffered until their newline arrives. Cancelled by the
    runner when the query completes."""
    offset = 0
    pending = ""
    while True:
        try:
            size = path.stat().st_size
        except OSError:
            await asyncio.sleep(interval)
            continue
        if size < offset:  # truncated (e.g. a fresh iteration's log)
            offset = 0
            pending = ""
        if size > offset:
            try:
                with path.open("r", errors="replace") as fh:
                    fh.seek(offset)
                    chunk = fh.read()
                    offset = fh.tell()
            except OSError:
                await asyncio.sleep(interval)
                continue
            pending += chunk
            *complete, pending = pending.split("\n")
            for line in complete:
                parsed = parse_progress_line(line)
                if parsed is not None:
                    emit({
                        "type": "rehearsal_progress",
                        "phase": phase,
                        **parsed,
                    })
        await asyncio.sleep(interval)


async def run(context: Context) -> None:
    if context.client is None:
        raise RuntimeError(
            "Phase 1: no agent client provided in context. The CLI is "
            "responsible for creating and passing through a ClaudeSDKClient."
        )

    artifact = context.phase_artifact(1)
    artifact.parent.mkdir(parents=True, exist_ok=True)

    exp_dir = exploration_dir(context.state_dir)
    exp_dir.mkdir(parents=True, exist_ok=True)
    # Clear stale shots so a re-run's filmstrip starts clean.
    for old in exp_dir.glob("*.png"):
        old.unlink()

    prompt = _build_prompt(context, exp_dir)

    seen: set[str] = set()
    watcher: asyncio.Task | None = None
    emit = context.event_emitter
    if emit is not None:
        watcher = asyncio.create_task(
            watch_screenshots(
                exp_dir, emit, seen,
                phase=1, url_prefix="/api/project/exploration",
            )
        )
    try:
        payload, result = await run_structured_query(
            context,
            prompt,
            session_id_for_phase(1, context.run_id),
            validate=_make_validator(exp_dir),
            phase_number=1,
        )
    finally:
        if watcher is not None and emit is not None:
            watcher.cancel()
            try:
                await watcher
            except asyncio.CancelledError:
                pass
            # Final scan: shots written inside the last poll interval.
            for name in new_screenshots(exp_dir, seen):
                emit(screenshot_event(
                    name, phase=1, url_prefix="/api/project/exploration",
                ))

    artifact.write_text(_render_view(payload, context))
    state_mod.record_phase_metrics(
        context.state_dir,
        1,
        intent_proposal=_normalized_proposal(payload),
        screens=payload.get("screens") or [],
        warnings=payload.get("warnings") or [],
    )
    record_phase_result(context, 1, result)
    print(summarize_run(1, artifact, result))
    shot_count = len(list(exp_dir.glob("*.png")))
    print(
        f"  ({len(payload.get('screens') or [])} screens, "
        f"{shot_count} screenshots, proposal: "
        f"{_normalized_proposal(payload)['goal'][:60]}...)"
    )
