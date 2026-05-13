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

import json
import re
import time
from typing import Any

from .. import prompts
from .. import state as state_mod
from ..agent_client import session_id_for_phase
from . import (
    Context,
    record_phase_result,
    run_query_on_client,
    summarize_run,
)


# Match the first ```json ... ``` fenced block anywhere in the
# response. Non-greedy body; tolerates optional language tag.
# Uses search (not match) so a prose preamble before the JSON
# block doesn't break parsing — the agent sometimes leads with
# a one-paragraph summary, and that's fine.
JSON_BLOCK_RE = re.compile(
    r"```(?:json)?\s*\n(.*?)\n```",
    re.DOTALL,
)

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


def _build_initial_prompt(phase3_text: str, url: str, phase3_path: str) -> str:
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
        "Emit the same two-part response: JSON findings block, then\n"
        "the per-segment markdown report."
    )


def _parse_findings(report_text: str) -> dict[str, Any] | None:
    """Extract the structured findings JSON from the agent's response.

    Searches for the first ```json fenced block anywhere in the text
    (the agent sometimes leads with a one-paragraph prose summary;
    that's fine). Returns the parsed dict on success, None when the
    response has no parseable JSON block. Callers fall back to
    LEGACY_DIRECTIVE_RE.
    """
    match = JSON_BLOCK_RE.search(report_text)
    if match is None:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


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


def _count_segments_from_phase3(phase3_text: str) -> int:
    """Best-effort segment count from the Phase 3 markdown. Used to
    size the per-iteration wall-clock budget before the first
    rehearsal — we don't have findings yet to count from.

    Falls back to 10 if parsing fails so the budget is reasonable
    rather than zero.
    """
    matches = re.findall(r"^###\s+Segment\s+\d+", phase3_text, re.MULTILINE)
    return len(matches) or 10


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

    segment_count = _count_segments_from_phase3(phase3_text)
    iteration_budget = _iteration_budget_s(segment_count)
    session_id = session_id_for_phase(4)

    findings: dict[str, Any] | None = None
    overall: str | None = None
    verified_text = ""
    prior_signature: frozenset[tuple[int, str]] | None = None

    for iteration in range(1, MAX_ITERATIONS + 1):
        if iteration == 1:
            prompt = _build_initial_prompt(phase3_text, context.url, str(phase3))
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

    # Persist findings + overall to state.json. Falls back to legacy
    # text directive parsing when the agent emitted no JSON block.
    if findings is not None:
        if overall is None:
            overall = _findings_overall(findings)
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
