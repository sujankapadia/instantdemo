"""Phase 4 — Explore the live application.

Reads the Phase 3 hypothesis plan and verifies each segment's
selectors against the running app via Playwright probes. Writes a
verified plan to `.instantdemo/phase4.md` that Phase 5 (Build)
consumes instead of the raw Phase 3 hypothesis.

The agent emits both a structured JSON findings block (top of the
response, fenced as ```json) and a human-readable per-segment
markdown body. The runner parses the JSON to decide whether the
pipeline halts (BLOCKED) or proceeds (OK).

Strict policy: any `FAIL_SELECTOR` or `FAIL_NARRATIVE` halts the
pipeline. No "soldier on" mode — better to surface what's wrong
than to bake a broken segment into the video.

Tools: Read (for phase3.md and the occasional source consult) and
Bash (for curl and a Playwright probe via python heredoc). No
Write — the runner saves the agent's response text to phase4.md.

See issue #48.
"""

from __future__ import annotations

import json
import re
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


# Match the first ```json ... ``` fenced block at the top of the
# response. Non-greedy body; tolerates optional language tag.
JSON_BLOCK_RE = re.compile(
    r"^\s*```(?:json)?\s*\n(.*?)\n```",
    re.DOTALL,
)

# Legacy fallback: parse the old text directive if no JSON block is
# present. Maps EXPLORE_OK/PARTIAL/BLOCKED to the new strict outcome.
LEGACY_DIRECTIVE_RE = re.compile(
    r"^\s*EXPLORE_(?P<directive>OK|PARTIAL|BLOCKED)(?:\s*[—:-]\s*.+)?\s*$",
    re.MULTILINE,
)


def _build_prompt(phase3_text: str, url: str, phase3_path: str) -> str:
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


def _parse_findings(report_text: str) -> dict[str, Any] | None:
    """Extract the structured findings JSON from the agent's response.

    Returns the parsed dict on success, None when the response has no
    parseable JSON block. Callers fall back to LEGACY_DIRECTIVE_RE.
    """
    match = JSON_BLOCK_RE.match(report_text)
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

    prompt = _build_prompt(phase3_text, context.url, str(phase3))
    verified_text, result = await run_query_on_client(
        context, prompt, session_id=session_id_for_phase(4)
    )

    if result is None:
        raise RuntimeError(
            "Phase 4: the Claude Agent SDK did not return a ResultMessage."
        )

    artifact.write_text(verified_text + "\n")
    record_phase_result(context, 4, result)
    print(summarize_run(4, artifact, result))

    # Parse the structured findings (or fall back to the legacy text
    # directive) and decide whether to halt the pipeline.
    findings = _parse_findings(verified_text)
    if findings is not None:
        overall = _findings_overall(findings)
        # Stash findings in state.json so the GUI can render the
        # triage panel without re-parsing phase4.md.
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

    if overall == "BLOCKED":
        # Build a concise list of failures for the error message.
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
