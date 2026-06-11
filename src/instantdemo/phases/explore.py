"""Phase 4 — Dress-rehearsal Explore phase.

Walks every segment in sequence against the live app via Playwright,
observes what actually happens at each step, and emits a verified
plan that Phase 5 (Build) consumes. The agent has authority to
revise selectors (Level 1) and reground narration (Level 2) when
its observations contradict the Phase 3 hypothesis. Structural
changes (Level 3 — drop / add / reorder segments) stay BLOCKED
with a humanized suggestion for the user.

Convergence: the runner allows up to MAX_ITERATIONS attempts. After
each rehearsal, if FAIL_* segments remain, the agent gets another
turn to revise. Stops early when:
  - All segments PASS (overall == OK)
  - The set of FAIL_* segments is identical to the prior iteration
    (no-progress detection)
  - The per-iteration wall-clock budget is exceeded
  - MAX_ITERATIONS is reached

Per-iteration wall-clock cap is `max(60, segment_count * 8)` seconds.
For an 8-segment shakedown that's 64s; for a 30-segment demo,
4 minutes. The cap protects against pathological agent loops, not
against legitimate execution time.

Artifacts:
  - .instantdemo/phase4.md — the final per-segment report (last
    iteration's response text)
  - .instantdemo/phase4-diff.md — per-segment changes Phase 4 made
    on top of Phase 3's hypothesis (selector swaps, narration
    regrounding). Written every run, even when no changes — see
    `_write_diff_artifact` for the empty-diff case.

Tools: Read (for phase3.md, intent.json, source context) and Bash
(for curl + the Playwright rehearsal script). No Write — the
runner saves the agent's response text to phase4.md.

See DRESS_REHEARSAL_DESIGN.md.
"""

from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path
from typing import Any

from .. import prompts, storyboard
from .. import state as state_mod
from ..actions import CANONICAL_ACTIONS
from ..agent_client import session_id_for_phase
from .analyze import new_screenshots, screenshot_event, watch_screenshots
from . import (
    Context,
    record_phase_result,
    run_query_on_client,
    summarize_run,
)

REHEARSAL_DIRNAME = "rehearsal"
_REHEARSAL_URL_PREFIX = "/api/project/rehearsal"

# Selectors that target <option> elements — hidden inside a closed
# <select> in Playwright's visibility model, so a visible-wait can
# never resolve (#67). Matches "option" as the element part of a
# selector ("#x option:nth-child(6)", "select > option", "option[v]").
_OPTION_SELECTOR_RE = re.compile(r"(?:^|[\s>+~])option\b")


def rehearsal_dir(state_dir: Path) -> Path:
    return state_dir / REHEARSAL_DIRNAME

# Legacy fallback: parse the old text directive if no JSON block is
# present. Maps EXPLORE_OK/PARTIAL/BLOCKED to the new strict outcome.
LEGACY_DIRECTIVE_RE = re.compile(
    r"^\s*EXPLORE_(?P<directive>OK|PARTIAL|BLOCKED)(?:\s*[—:-]\s*.+)?\s*$",
    re.MULTILINE,
)


# Convergence guarantees — see DRESS_REHEARSAL_DESIGN.md "Convergence
# guarantees" section. These are runner-enforced caps, independent of
# the agent's in-query revision behavior.
#
# Important: the budget is a SOFT ceiling — we only check it between
# iterations, never mid-iteration. Hard-cancelling an in-flight SDK
# call (asyncio.wait_for) nukes everything: no findings, no cost
# recorded, no artifact. "Slow-but-working" must not turn into
# "complete failure". The agent SDK has its own per-tool-call
# timeouts that bound pathological behavior at finer granularity.
MAX_ITERATIONS = 3
# Floor: long enough for a single rehearsal of a small demo. An 8-
# segment rehearsal script can take 60-90s of pure Playwright wall-
# clock (up to 10s wait_for per segment) before any agent thinking.
_PER_ITERATION_FLOOR_S = 180
# Per-segment additional budget — covers script execution + agent
# analysis + JSON emission overhead.
_PER_SEGMENT_BUDGET_S = 25


def _iteration_budget_s(segment_count: int) -> float:
    """Per-iteration wall-clock budget. Scales with segment count so
    long demos aren't artificially gated; floors at 60s so small
    demos still get a tight ceiling on pathological agent loops.
    """
    return max(_PER_ITERATION_FLOOR_S, segment_count * _PER_SEGMENT_BUDGET_S)


def _build_initial_prompt(
    doc: dict,
    url: str,
    phase3_path: str,
    shots_dir: Path,
    section: str | None = None,
) -> str:
    """The plan is rendered FROM the storyboard (not read from
    phase3.md on disk) so the prompt is guaranteed consistent with
    the canonical document. When scoped to a chapter (M5b), the
    scenes BEFORE the chapter are presented as verified setup steps
    to replay without verification; scenes after it are omitted."""
    template = prompts.load("phase4")
    # str.replace, not str.format — the template contains JSON braces.
    template = template.replace("{rehearsal_dir}", str(shots_dir))
    if not section:
        return (
            f"The app being demoed is running at: {url}\n"
            f"The Phase 3 plan is at: {phase3_path}\n"
            "\n"
            "The following is the Phase 3 hypothesis plan. Each segment\n"
            "has a primary selector derived from source code and (often)\n"
            "fallback selectors on its 'Selector fallbacks' line.\n"
            "\n"
            "---\n"
            f"{storyboard.render_phase3_view(doc)}\n"
            "---\n"
            "\n"
            f"{template}"
        )

    scenes = doc["scenes"]
    positions = [
        i for i, s in enumerate(scenes) if s.get("section") == section
    ]
    if not positions:
        raise RuntimeError(f"no chapter named {section!r} in the storyboard")
    prefix_doc = dict(doc, scenes=scenes[: positions[0]])
    chapter_doc = dict(doc, scenes=scenes[positions[0] : positions[-1] + 1])
    prefix_block = (
        "These VERIFIED SETUP segments come before the chapter. Replay\n"
        "their actions in order with brief waits (their selectors are\n"
        "already verified — do NOT re-verify, screenshot, or report\n"
        "findings for them; they only get the app to the chapter's\n"
        "starting state):\n"
        "\n"
        "---\n"
        f"{storyboard.render_phase3_view(prefix_doc)}\n"
        "---\n"
        "\n"
        if positions[0] > 0
        else "This chapter OPENS the film — no setup segments.\n\n"
    )
    return (
        f"The app being demoed is running at: {url}\n"
        f"The Phase 3 plan is at: {phase3_path}\n"
        "\n"
        f"This is a CHAPTER REVISION: rehearse and verify ONLY the\n"
        f"\"{section}\" chapter's segments below. Report findings (and\n"
        "save rehearsal screenshots) for those segments ONLY, keyed by\n"
        "the indices shown.\n"
        "\n"
        f"{prefix_block}"
        "The chapter under rehearsal — each segment has a primary\n"
        "selector and (often) fallbacks:\n"
        "\n"
        "---\n"
        f"{storyboard.render_phase3_view(chapter_doc)}\n"
        "---\n"
        "\n"
        f"{template}"
    )


def _build_retry_prompt(prior_findings: dict[str, Any], iteration: int) -> str:
    """Continuation prompt for iteration 2+. The session retains the
    full prior conversation, so this is short — just a nudge to
    reflect on what failed and try again within authority.
    """
    failure_lines: list[str] = []
    for seg in prior_findings.get("segments") or []:
        status = seg.get("status", "")
        if status in ("FAIL_SELECTOR", "FAIL_NARRATIVE"):
            idx = seg.get("index", "?")
            reason = seg.get("reason", "")
            failure_lines.append(f"  - Segment {idx} ({status}): {reason}")
    failures = "\n".join(failure_lines) or "(see prior findings)"
    return (
        f"Iteration {iteration} of up to {MAX_ITERATIONS}. The previous\n"
        f"rehearsal reported the following failures:\n"
        f"{failures}\n"
        "\n"
        "Reflect on what you observed. If you can address these within\n"
        "your authority (Level 1 mechanical or Level 2 narration\n"
        "regrounding), revise and re-rehearse. If you've concluded the\n"
        "issue is structural (Level 3 — drop / add / reorder segments)\n"
        "or the live app doesn't support what the demo needs, re-emit\n"
        "your findings unchanged — the runner will surface them to the\n"
        "user as BLOCKED with your suggestions.\n"
        "\n"
        "End your response with the single updated fenced JSON\n"
        "findings block (the runner renders the human report from it)."
    )


def _parse_findings(report_text: str) -> dict[str, Any] | None:
    """Extract the structured findings JSON from the agent's response.

    Delegates to storyboard.extract_json_block: first parseable
    fenced JSON object anywhere in the text (prose preambles are
    fine). Returns None when absent; callers fall back to
    LEGACY_DIRECTIVE_RE.
    """
    return storyboard.extract_json_block(report_text)


def _findings_overall(findings: dict[str, Any]) -> str:
    """Derive the overall outcome from structured findings — runner's
    deterministic policy, NOT the agent's self-reported overall field.

    The agent's `summary.overall` is informational; the runner trusts
    the per-segment statuses. If any segment has FAIL_*, we halt.
    """
    segments = findings.get("segments") or []
    for seg in segments:
        if seg.get("status") in ("FAIL_SELECTOR", "FAIL_NARRATIVE"):
            return "BLOCKED"
    return "OK"


def _legacy_overall(report_text: str) -> str:
    """Backwards-compat: older Phase 4 outputs only had an
    EXPLORE_OK/PARTIAL/BLOCKED text directive. Map to the strict
    runner policy: PARTIAL counts as BLOCKED (any reported failure
    halts the pipeline).
    """
    matches = list(LEGACY_DIRECTIVE_RE.finditer(report_text))
    if not matches:
        # Agent emitted neither JSON nor legacy directive — defensive
        # default to BLOCKED so the user investigates.
        return "BLOCKED"
    directive = matches[-1].group("directive")
    return "OK" if directive == "OK" else "BLOCKED"


def _failure_signature(findings: dict[str, Any]) -> frozenset[tuple[int, str]]:
    """Frozenset of (segment_index, status) tuples for FAIL_* segments.

    Used for no-progress detection: if iteration N produces the same
    signature as N-1, the agent isn't making progress and re-running
    won't help — break out of the convergence loop.
    """
    sig: set[tuple[int, str]] = set()
    for seg in findings.get("segments") or []:
        status = seg.get("status", "")
        if status in ("FAIL_SELECTOR", "FAIL_NARRATIVE"):
            idx = seg.get("index")
            if isinstance(idx, int):
                sig.add((idx, status))
    return frozenset(sig)


_FINDING_STATUS_TO_SCENE = {
    "PASS": "verified",
    "WARN": "warn",
    "FAIL_SELECTOR": "failed",
    "FAIL_NARRATIVE": "failed",
}


def merge_findings_into_storyboard(
    doc: dict, findings: dict[str, Any], *, iteration: int,
    scope_indices: set[int] | None = None,
) -> list[str]:
    """Apply the final findings to the storyboard scenes. Pure
    function (unit-tested); returns human-readable warnings for
    findings that couldn't be applied (e.g. out-of-range index).

    Findings are index-keyed (1-based, matching scene.index) for
    GUI/state.json compatibility. Applied per segment:
      - selector_swapped  → scene.selector = [to] + revision entry
        (the rehearsal verified exactly ONE selector; stale fallbacks
        that already failed would only burn renderer timeout budget)
      - narration_revised → scene.narration = narration_to + revision
      - updates.action (+ key) → apply when canonical + revision
        (action-kind change on the same element, e.g. click →
        press-Escape — Level-1 mechanical; see #67)
      - updates.wait_for / updates.pause_after_ms → apply + revision
        (the Level-1 timing channel — without it, refinements would
        be lost now that Phase 5 is deterministic). wait_for values
        targeting <option> elements are refused (never visible).
      - status / verification from the finding status
    """
    warnings: list[str] = []
    scenes = doc.get("scenes", [])
    for finding in findings.get("segments") or []:
        idx = finding.get("index")
        if not isinstance(idx, int) or not (1 <= idx <= len(scenes)):
            warnings.append(
                f"finding index {idx!r} out of range (1..{len(scenes)}) — skipped"
            )
            continue
        if scope_indices is not None and idx not in scope_indices:
            # Scoped chapter rehearsal (M5b): scenes outside the
            # chapter are verified and recorded — a finding against
            # them exceeds the rehearsal's authority.
            warnings.append(
                f"finding {idx} is outside the revised chapter — ignored"
            )
            continue
        scene = scenes[idx - 1]
        revisions = scene.setdefault("revisions", [])
        reason = finding.get("reason", "")

        if finding.get("selector_swapped"):
            new_selector = (finding.get("to") or "").strip()
            if new_selector:
                revisions.append({
                    "type": "selector",
                    "from": finding.get("from", ""),
                    "to": new_selector,
                    "reason": reason,
                    "iteration": iteration,
                    "phase": 4,
                })
                scene["selector"] = [new_selector]
            else:
                warnings.append(
                    f"segment {idx}: selector_swapped without 'to' — skipped"
                )

        if finding.get("narration_revised"):
            new_narration = finding.get("narration_to")
            if isinstance(new_narration, str):
                revisions.append({
                    "type": "narration",
                    "from": scene.get("narration", ""),
                    "to": new_narration,
                    "reason": reason,
                    "iteration": iteration,
                    "phase": 4,
                })
                scene["narration"] = new_narration
            else:
                warnings.append(
                    f"segment {idx}: narration_revised without "
                    "'narration_to' — skipped"
                )

        updates = finding.get("updates") or {}
        if "action" in updates:
            # Action-KIND revision on the same UI element (e.g.
            # click → press-Escape) — Level-1 mechanical in spirit:
            # the scene's purpose is unchanged, only how it's
            # performed. Validated against the closed action
            # contract; anything non-canonical is refused loudly.
            # (Issue #67: this used to be silently dropped, losing a
            # rehearsal-VERIFIED fix and guaranteeing a drift block.)
            new_action = updates["action"]
            if new_action in CANONICAL_ACTIONS:
                old_action = scene.get("action", "")
                new_key = updates.get("key")
                revisions.append({
                    "type": "action",
                    "from": old_action,
                    "to": new_action
                    + (f" {new_key}" if isinstance(new_key, str) else ""),
                    "reason": reason,
                    "iteration": iteration,
                    "phase": 4,
                })
                scene["action"] = new_action
                if isinstance(new_key, str):
                    scene["key"] = new_key
                elif new_action != "press":
                    scene.pop("key", None)
            else:
                warnings.append(
                    f"segment {idx}: updates.action {new_action!r} is not "
                    "a canonical action — skipped"
                )
        if "wait_for" in updates:
            new_wait = storyboard.normalize_candidates(updates["wait_for"])
            unwaitable = [s for s in new_wait if _OPTION_SELECTOR_RE.search(s)]
            if unwaitable:
                # <option> elements inside a closed <select> are
                # hidden in Playwright's visibility model — the
                # renderer's visible-wait can never resolve (#67).
                warnings.append(
                    f"segment {idx}: wait_for targets <option> elements "
                    f"({', '.join(unwaitable)}) which can never become "
                    "visible — skipped; keeping the existing wait"
                )
            elif new_wait:
                revisions.append({
                    "type": "wait_for",
                    "from": ", ".join(
                        storyboard.normalize_candidates(scene.get("wait_for"))
                    ),
                    "to": ", ".join(new_wait),
                    "reason": reason,
                    "iteration": iteration,
                    "phase": 4,
                })
                scene["wait_for"] = new_wait
        if "pause_after_ms" in updates:
            pause = updates["pause_after_ms"]
            if isinstance(pause, int):
                revisions.append({
                    "type": "pause_after_ms",
                    "from": str(scene.get("pause_after_ms", "")),
                    "to": str(pause),
                    "reason": reason,
                    "iteration": iteration,
                    "phase": 4,
                })
                scene["pause_after_ms"] = pause

        status = finding.get("status", "")
        scene["status"] = _FINDING_STATUS_TO_SCENE.get(status, "failed")
        scene["verification"] = {
            "status": status,
            "reason": reason,
            "suggestion": finding.get("suggestion"),
        }
    return warnings


def _write_diff_artifact(
    state_dir: Any, findings: dict[str, Any] | None
) -> None:
    """Write `.instantdemo/phase4-diff.md` summarizing per-segment
    revisions Phase 4 made to the Phase 3 hypothesis.

    Always writes the file (even when no revisions) so downstream
    tooling can rely on its presence.

    The agent emits `from`/`to` (selector) and `narration_from`/
    `narration_to` directly in the findings — no need to re-parse
    Phase 3's markdown.
    """
    diff_path = state_dir / "phase4-diff.md"

    if findings is None:
        diff_path.write_text(
            "# Phase 4 revisions\n\n"
            "No structured findings available — the agent did not\n"
            "emit a parseable JSON block. See `phase4.md` for the\n"
            "raw response.\n"
        )
        return

    selector_swaps: list[str] = []
    narration_changes: list[str] = []

    for seg in findings.get("segments") or []:
        idx = seg.get("index", "?")

        if seg.get("selector_swapped"):
            from_sel = seg.get("from", "")
            to_sel = seg.get("to", "")
            selector_swaps.append(
                f"### Segment {idx} — selector swap\n\n"
                f"- **From:** `{from_sel}`\n"
                f"- **To:** `{to_sel}`\n"
                f"- **Reason:** {seg.get('reason', '')}\n"
            )

        if seg.get("narration_revised"):
            n_from = seg.get("narration_from", "")
            n_to = seg.get("narration_to", "")
            narration_changes.append(
                f"### Segment {idx} — narration regrounded\n\n"
                f"- **From:** {n_from!r}\n"
                f"- **To:** {n_to!r}\n"
                f"- **Reason:** {seg.get('reason', '')}\n"
            )

    if not selector_swaps and not narration_changes:
        diff_path.write_text(
            "# Phase 4 revisions\n\n"
            "No revisions — the Phase 3 hypothesis matched the live\n"
            "app and the narration matched what was observed.\n"
        )
        return

    parts: list[str] = ["# Phase 4 revisions"]
    if selector_swaps:
        parts.append("## Selector swaps")
        parts.extend(selector_swaps)
    if narration_changes:
        parts.append("## Narration regrounding")
        parts.extend(narration_changes)
    diff_path.write_text("\n\n".join(parts))


def link_rehearsal_screenshots(doc: dict, shots_dir: Path) -> list[str]:
    """Join rehearsal screenshots to scenes by SCENE-ID naming
    (`<id>.png`, e.g. s12.png — M5b). Ids are stable and never
    reused, so a scoped re-plan can't collide thumbnails the way
    shifting indices would. Pure function (unit-tested). Sets each
    scene's `rehearsal_screenshot` when the file exists and POPS it
    when it doesn't — a prior run's storyboard must not carry stale
    refs into the gate. Returns the linked filenames."""
    linked: list[str] = []
    existing: set[str] = set()
    if shots_dir.is_dir():
        existing = {p.name for p in shots_dir.glob("s*.png")}
    for scene in doc.get("scenes", []):
        name = f"{scene['id']}.png"
        if name in existing:
            scene["rehearsal_screenshot"] = name
            linked.append(name)
        else:
            scene.pop("rehearsal_screenshot", None)
    return linked


async def _ensure_screenshots(
    context: Context,
    session_id: str,
    shots_dir: Path,
    findings: dict[str, Any],
) -> None:
    """At-least-one screenshot enforcement (the M1 pattern adapted to
    Phase 4's convergence loop): if the rehearsal verified segments
    but saved zero shots, spend ONE short corrective turn asking for
    a minimal screenshot pass — then continue regardless. Thumbnails
    are presentation, not correctness; this never fails the phase."""
    has_passing = any(
        f.get("status") in ("PASS", "WARN")
        for f in findings.get("segments") or []
    )
    has_shots = shots_dir.is_dir() and any(shots_dir.glob("s*.png"))
    if not has_passing or has_shots:
        return
    print("[Phase 4] no rehearsal screenshots saved — one corrective turn")
    _text, result = await run_query_on_client(
        context,
        (
            "You verified segments but saved no rehearsal screenshots. "
            "Run one minimal Playwright pass that walks the verified "
            "plan and saves a screenshot per passing segment as "
            f"{shots_dir}/s<N>.png (s1.png, s2.png, ...). Do not "
            "re-verify or change findings — just capture the screens. "
            "Reply with a one-line confirmation when done."
        ),
        session_id=session_id,
    )
    if result is None or not (
        shots_dir.is_dir() and any(shots_dir.glob("s*.png"))
    ):
        print(
            "[Phase 4] WARNING: still no rehearsal screenshots — "
            "storyboard cards will show placeholders."
        )


async def run(context: Context) -> None:
    if context.client is None:
        raise RuntimeError(
            "Phase 4: no agent client provided in context. The CLI is "
            "responsible for creating and passing through a ClaudeSDKClient."
        )

    doc = storyboard.load(context.state_dir)
    section = context.section_scope
    scope_indices: set[int] | None = None
    if section:
        scope_indices = {
            s["index"] for s in doc["scenes"] if s.get("section") == section
        }
        if not scope_indices:
            raise RuntimeError(
                f"Phase 4 (scoped): no chapter named {section!r}"
            )

    artifact = context.phase_artifact(4)
    artifact.parent.mkdir(parents=True, exist_ok=True)

    shots_dir = rehearsal_dir(context.state_dir)
    shots_dir.mkdir(parents=True, exist_ok=True)
    # Clear stale shots so the gate never shows a prior run's screens.
    # Scoped (M5b): out-of-scope scenes keep their thumbnails (they
    # aren't re-rehearsed); only files no longer backed by a current
    # scene id are stale — which covers the replaced chapter's
    # retired ids.
    if section:
        live_ids = {s["id"] for s in doc["scenes"]}
        for old in shots_dir.glob("*.png"):
            if old.stem not in live_ids:
                old.unlink()
    else:
        for old in shots_dir.glob("*.png"):
            old.unlink()

    segment_count = (
        len(scope_indices) if scope_indices else len(doc["scenes"])
    )
    iteration_budget = _iteration_budget_s(segment_count)
    session_id = session_id_for_phase(4, context.run_id)

    seen_shots: set[str] = set()
    watcher: asyncio.Task | None = None
    emit = context.event_emitter
    if emit is not None:
        watcher = asyncio.create_task(
            watch_screenshots(
                shots_dir, emit, seen_shots,
                phase=4, url_prefix=_REHEARSAL_URL_PREFIX,
            )
        )

    findings: dict[str, Any] | None = None
    overall: str | None = None
    verified_text = ""
    prior_signature: frozenset[tuple[int, str]] | None = None
    final_iteration = 0

    try:
        for iteration in range(1, MAX_ITERATIONS + 1):
            final_iteration = iteration
            if iteration == 1:
                prompt = _build_initial_prompt(
                    doc, context.url, str(context.phase_artifact(3)),
                    shots_dir, section,
                )
            else:
                assert findings is not None  # only retry after a parsed iteration
                prompt = _build_retry_prompt(findings, iteration)

            start_ts = time.monotonic()
            # Soft ceiling: the SDK call runs to completion. We check
            # elapsed AFTER the call and only refuse to start iteration
            # N+1 if N already overran. Mid-call hard cancellation would
            # discard all in-flight work.
            verified_text, result = await run_query_on_client(
                context, prompt, session_id=session_id
            )
            elapsed = time.monotonic() - start_ts

            if result is None:
                raise RuntimeError(
                    "Phase 4: the Claude Agent SDK did not return a "
                    f"ResultMessage on iteration {iteration}."
                )

            # Persist this iteration's text as the artifact (later iterations
            # overwrite earlier ones — phase4.md always reflects the LAST
            # rehearsal's report). Record metrics for cost / token tracking.
            artifact.write_text(verified_text + "\n")
            record_phase_result(context, 4, result)
            print(
                summarize_run(4, artifact, result)
                + f" [iter {iteration}, {elapsed:.1f}s]"
            )

            findings = _parse_findings(verified_text)
            if findings is None:
                # No parseable findings — defer to legacy directive logic
                # below. Don't iterate further; structured iteration
                # requires structured findings.
                break

            overall = _findings_overall(findings)
            if overall == "OK":
                break

            signature = _failure_signature(findings)
            if signature == prior_signature:
                print(
                    f"[Phase 4] iteration {iteration} produced the same "
                    "FAIL signature as the prior iteration — no progress, "
                    "stopping."
                )
                break
            prior_signature = signature

            # Soft ceiling check: if this iteration overran its budget,
            # don't start the next one. The current iteration's work is
            # preserved (artifact written, cost recorded).
            if elapsed > iteration_budget:
                print(
                    f"[Phase 4] iteration {iteration} took {elapsed:.1f}s, "
                    f"exceeding the {iteration_budget:.0f}s soft budget; "
                    "not starting another iteration."
                )
                break

        # Screenshot enforcement (one corrective turn, never fails the
        # phase) runs while the watcher is still streaming.
        if findings is not None:
            await _ensure_screenshots(
                context, session_id, shots_dir, findings
            )
    finally:
        if watcher is not None and emit is not None:
            watcher.cancel()
            try:
                await watcher
            except asyncio.CancelledError:
                pass
            # Final scan: shots written inside the last poll interval.
            for name in new_screenshots(shots_dir, seen_shots):
                emit(screenshot_event(
                    name, phase=4, url_prefix=_REHEARSAL_URL_PREFIX,
                ))

    # Persist findings + overall to state.json. Falls back to legacy
    # text directive parsing when the agent emitted no JSON block.
    if findings is not None:
        if overall is None:
            overall = _findings_overall(findings)

        # Merge the FINAL findings into the storyboard — once, after
        # the convergence loop (findings are cumulative across
        # iterations), and BEFORE the BLOCKED raise so failure state
        # is captured in the canonical document. phase4.md becomes
        # the rendered view of the merged result.
        merge_warnings = merge_findings_into_storyboard(
            doc, findings, iteration=final_iteration,
            scope_indices=scope_indices,
        )
        for warning in merge_warnings:
            print(f"[Phase 4] merge warning: {warning}")
        linked = link_rehearsal_screenshots(doc, shots_dir)
        print(f"[Phase 4] rehearsal screenshots linked: {len(linked)}")
        storyboard.save(context.state_dir, doc)
        artifact.write_text(storyboard.render_phase4_view(doc, findings))

        state_mod.record_phase_metrics(
            context.state_dir,
            4,
            explore_findings=findings,
            explore_overall=overall,
        )
    else:
        overall = _legacy_overall(verified_text)
        state_mod.record_phase_metrics(
            context.state_dir,
            4,
            explore_overall=overall,
        )

    # Diff artifact — always emit, even when no revisions or no
    # parseable findings (the file documents the no-op case).
    _write_diff_artifact(context.state_dir, findings)

    if overall == "BLOCKED":
        failures: list[str] = []
        if findings is not None:
            for seg in findings.get("segments") or []:
                status = seg.get("status", "")
                if status in ("FAIL_SELECTOR", "FAIL_NARRATIVE"):
                    idx = seg.get("index", "?")
                    reason = seg.get("reason", "")
                    failures.append(f"  - Segment {idx} ({status}): {reason}")
        detail = "\n".join(failures) if failures else "(see phase4.md for details)"
        raise RuntimeError(
            f"Phase 4 (Explore) found issues that block the render:\n"
            f"{detail}\n"
            f"See {artifact} for the full report and suggested fixes."
        )
