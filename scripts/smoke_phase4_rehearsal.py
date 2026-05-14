#!/usr/bin/env python3
"""End-to-end smoke check for the dress-rehearsal Phase 4.

Restores the saved shakedown fixture (which already has phase1.md
through phase3.md, plus intent.json and a demo-script.json), spawns
`instantdemo serve` against it, kicks off a Phase-4-only run via
the API, watches the SSE stream to completion, and asserts the
rehearsal produced a clean OK overall.

Prerequisite: the **claude-code-analytics** app must be running at
`http://localhost:8000` (the fixture's target URL). Without it the
rehearsal will fail at the curl drift check. The smoke pre-flights
this and exits early with a clear message rather than burning agent
cost on a doomed run.

Cost: roughly $0.30-0.50 in Claude usage per invocation
(~1-3 minutes wall time, depending on convergence).

Requires:
    - instantdemo[gui,dev] installed
    - `claude` CLI authenticated, or ANTHROPIC_API_KEY with credit
    - claude-code-analytics running locally on port 8000

Exit code:
    0  smoke pass
    1  smoke fail
    2  preconditions unmet (fixture missing, target app down)

Per DRESS_REHEARSAL_DESIGN.md success criteria.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = (
    REPO_ROOT
    / "fixtures"
    / "shakedown-active-sessions-exclude-recently-ended-2026-05-12"
)
TARGET_URL = "http://localhost:8000"


def find_free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_health(base_url: str, timeout_s: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"{base_url}/api/health", timeout=1.0)
            if r.status_code == 200:
                return True
        except (httpx.RequestError, httpx.ReadTimeout):
            pass
        time.sleep(0.5)
    return False


def target_app_reachable() -> bool:
    try:
        r = httpx.get(TARGET_URL, timeout=2.0)
        return r.status_code < 500
    except (httpx.RequestError, httpx.ReadTimeout):
        return False


def apply_scenario_5b(phase3_path: Path) -> None:
    """Break Segment 2's selector and remove its fallback so the
    rehearsal has nothing to swap in. Expected outcome: BLOCKED
    with FAIL_SELECTOR on segment 2.
    """
    text = phase3_path.read_text()
    # Replace Segment 2's selector
    text = text.replace(
        '- **Selector:** `a[href="/active"]`',
        '- **Selector:** `a[href="/totally-nonexistent-route-xyz"]`',
        1,
    )
    # Strip Segment 2's fallback note so the agent has nothing to try.
    # Match the Notes line for Segment 2 and replace the fallback clause.
    text = re.sub(
        r'(\*\*Notes:\*\* `NavLink to="/active"` renders an `<a href="/active">`\. '
        r'Client-side route — no full reload\.) Fallback: `aside a:has-text\("Active"\)`\.',
        r"\1 (No fallback available — this segment must work as-is.)",
        text,
        count=1,
    )
    phase3_path.write_text(text)


def apply_scenario_5c(phase3_path: Path) -> None:
    """Inject an overclaim into Segment 4's narration that the rehearsal
    can verify is false by observation. The active-session card does NOT
    have a "real-time terminal view"; the cards show project name,
    runtime, and a recent-messages preview. Expected outcome: either
    PASS + narration_revised=True (regrounded) or FAIL_NARRATIVE.
    """
    text = phase3_path.read_text()
    original = (
        '- **Narration:** "Each card is one running process. I get the '
        "project name, how long it's been going, and a preview of the most "
        'recent messages — so I can tell at a glance what each session is '
        'actually doing."'
    )
    overclaim = (
        '- **Narration:** "Each card is one running process. I get the '
        "project name, how long it's been going, and a real-time terminal "
        "view streaming every command the AI is running right now — so I can "
        'watch each session work in real time."'
    )
    if original not in text:
        raise RuntimeError(
            "5c setup: could not find Segment 4 narration to replace "
            "in phase3.md — fixture may have drifted."
        )
    text = text.replace(original, overclaim, 1)
    phase3_path.write_text(text)


async def run_smoke(scenario: str) -> int:
    if not FIXTURE.exists():
        print(
            f"[smoke] PRECONDITION: fixture missing at {FIXTURE}",
            file=sys.stderr,
        )
        return 2

    if not target_app_reachable():
        print(
            f"[smoke] PRECONDITION: target app at {TARGET_URL} is "
            "unreachable. Start claude-code-analytics (API on 8000 "
            "+ frontend on 5173) and rerun.",
            file=sys.stderr,
        )
        return 2

    tmp_root = Path(
        tempfile.mkdtemp(prefix=f"instantdemo-smoke-phase4-{scenario}-")
    )
    # Copy fixture contents (including .instantdemo/) to tmp_root.
    for entry in FIXTURE.iterdir():
        dest = tmp_root / entry.name
        if entry.is_dir():
            shutil.copytree(entry, dest)
        else:
            shutil.copy2(entry, dest)
    state_dir = tmp_root / ".instantdemo"
    phase3_path = state_dir / "phase3.md"

    if scenario == "5b":
        apply_scenario_5b(phase3_path)
        print("[smoke] Scenario 5b: broke Segment 2 selector + removed fallback")
    elif scenario == "5c":
        apply_scenario_5c(phase3_path)
        print("[smoke] Scenario 5c: injected overclaim into Segment 4 narration")

    port = find_free_port()
    base_url = f"http://127.0.0.1:{port}"
    print(f"[smoke] Project: {tmp_root}")
    print(f"[smoke] Port:    {port}")

    server = subprocess.Popen(
        [
            "instantdemo",
            "serve",
            "--project",
            str(tmp_root),
            "--port",
            str(port),
            "--no-open",
        ],
        env=os.environ.copy(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    if not wait_for_health(base_url):
        print("[smoke] FAIL: server did not become healthy", file=sys.stderr)
        server.terminate()
        return 1

    print("[smoke] Server ready. Starting Phase 4 dress rehearsal.")

    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=600.0) as client:
            resp = await client.post(
                "/api/runs",
                json={"phases": [4], "url": TARGET_URL},
            )
            if resp.status_code != 202:
                print(
                    f"[smoke] FAIL: POST /api/runs returned {resp.status_code}: "
                    f"{resp.text}",
                    file=sys.stderr,
                )
                return 1
            run_id = resp.json()["run_id"]
            print(f"[smoke] Run id: {run_id}")

            event_types: list[str] = []
            terminal_events = {"run_complete", "run_canceled", "run_error"}
            run_start = time.monotonic()
            async with client.stream(
                "GET", f"/api/runs/{run_id}/stream"
            ) as r:
                async for line in r.aiter_lines():
                    if line.startswith("data: "):
                        data = line[len("data: ") :].strip()
                        if not data:
                            continue
                        try:
                            event = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        evt_type = event.get("type")
                        if evt_type:
                            event_types.append(evt_type)
                            if evt_type in terminal_events:
                                break
            duration_s = time.monotonic() - run_start

            print(f"[smoke] Events:  {event_types}")
            print(f"[smoke] Run wall-clock: {duration_s:.1f}s")

            errors: list[str] = []
            warnings: list[str] = []

            # Expected outcomes per scenario:
            #   5a: clean PASS — overall=OK, status=completed
            #   5b: bimodal — OK if the agent recovers (e.g. invents
            #       a working selector from source); BLOCKED if it
            #       cannot. Both are valid architectural behavior;
            #       the seg-specific check below catches the case
            #       where the broken selector wasn't acted on at all.
            #   5c: bimodal — OK if regrounded (PASS+narration_revised
            #       on seg 4) or BLOCKED if unfixable (FAIL_NARRATIVE
            #       on seg 4). The seg-specific check below catches
            #       both.
            if scenario == "5a":
                required_events: tuple[str, ...] = (
                    "phase_started",
                    "phase_complete",
                    "run_complete",
                )
            else:
                required_events = ("phase_started",)
            for required in required_events:
                if required not in event_types:
                    errors.append(f"missing event: {required}")

            state_path = state_dir / "state.json"
            if not state_path.exists():
                errors.append("state.json was not created")
            else:
                state = json.loads(state_path.read_text())
                phase4 = (state.get("phases") or {}).get("4") or {}

                # For 5a we require strict completion; 5b/5c accept
                # either completion (agent self-recovered) or error
                # (agent surfaced a clean FAIL_*).
                if scenario == "5a":
                    if phase4.get("status") != "completed":
                        errors.append(
                            f"phases.4.status expected 'completed', got "
                            f"{phase4.get('status')!r}"
                        )
                    if phase4.get("explore_overall") != "OK":
                        errors.append(
                            f"phases.4.explore_overall expected 'OK', got "
                            f"{phase4.get('explore_overall')!r}"
                        )
                else:
                    if phase4.get("status") not in ("completed", "error"):
                        errors.append(
                            f"phases.4.status expected 'completed' or "
                            f"'error', got {phase4.get('status')!r}"
                        )
                    if phase4.get("explore_overall") not in ("OK", "BLOCKED"):
                        errors.append(
                            f"phases.4.explore_overall expected 'OK' or "
                            f"'BLOCKED', got {phase4.get('explore_overall')!r}"
                        )

                cost = phase4.get("cost_usd") or 0
                if cost <= 0:
                    errors.append(
                        f"phases.4.cost_usd expected > 0, got {cost}"
                    )
                elif cost > 0.60:
                    warnings.append(
                        f"phases.4.cost_usd ${cost:.4f} exceeds the "
                        "$0.60 ceiling (allow some slack for multi-iter)"
                    )

                # Scenario-specific structural checks
                findings = phase4.get("explore_findings") or {}
                segments = findings.get("segments") or []
                if scenario == "5b":
                    seg2 = next(
                        (s for s in segments if s.get("index") == 2),
                        None,
                    )
                    if seg2 is None:
                        errors.append("5b: segment 2 missing from findings")
                    else:
                        status = seg2.get("status")
                        swapped = seg2.get("selector_swapped", False)
                        if status == "PASS" and swapped:
                            pass  # agent recovered — Level 1.5 behavior
                        elif status == "FAIL_SELECTOR":
                            pass  # acceptable outcome (strict reading)
                        else:
                            errors.append(
                                f"5b expected segment 2 to be "
                                f"PASS+selector_swapped or FAIL_SELECTOR; "
                                f"got status={status!r}, "
                                f"selector_swapped={swapped!r}"
                            )
                elif scenario == "5c":
                    seg4 = next(
                        (s for s in segments if s.get("index") == 4),
                        None,
                    )
                    if seg4 is None:
                        errors.append("5c: segment 4 missing from findings")
                    else:
                        status = seg4.get("status")
                        regrounded = seg4.get("narration_revised", False)
                        if status == "PASS" and regrounded:
                            pass  # ideal outcome
                        elif status == "FAIL_NARRATIVE":
                            pass  # acceptable outcome
                        else:
                            errors.append(
                                f"5c expected segment 4 to be "
                                f"PASS+narration_revised or "
                                f"FAIL_NARRATIVE; got status={status!r}, "
                                f"narration_revised={regrounded!r}"
                            )

            artifact = state_dir / "phase4.md"
            if not artifact.exists():
                errors.append("phase4.md was not written")
            elif "```json" not in artifact.read_text():
                errors.append("phase4.md has no JSON findings block")

            diff = state_dir / "phase4-diff.md"
            if not diff.exists():
                errors.append("phase4-diff.md was not written")

            if errors:
                print("[smoke] FAIL:", file=sys.stderr)
                for err in errors:
                    print(f"  - {err}", file=sys.stderr)
                return 1

            phase4_data = json.loads(state_path.read_text())["phases"]["4"]
            cost = phase4_data["cost_usd"]
            duration_ms = phase4_data.get("duration_ms") or 0
            findings = phase4_data.get("explore_findings") or {}
            summary = findings.get("summary") or {}
            n_swaps = sum(
                1
                for s in (findings.get("segments") or [])
                if s.get("selector_swapped")
            )
            n_regrnd = sum(
                1
                for s in (findings.get("segments") or [])
                if s.get("narration_revised")
            )
            n_fail_sel = sum(
                1
                for s in (findings.get("segments") or [])
                if s.get("status") == "FAIL_SELECTOR"
            )
            n_fail_nar = sum(
                1
                for s in (findings.get("segments") or [])
                if s.get("status") == "FAIL_NARRATIVE"
            )

            overall = phase4_data.get("explore_overall", "?")
            print(
                f"[smoke] PASS  — scenario {scenario}: phase 4 "
                f"{overall} "
                f"({summary.get('pass', '?')}/{summary.get('total', '?')} PASS, "
                f"{n_fail_sel} FAIL_SELECTOR, "
                f"{n_fail_nar} FAIL_NARRATIVE, "
                f"{n_swaps} selector swaps, "
                f"{n_regrnd} narration regroundings) "
                f"(${cost:.4f}, {duration_ms / 1000:.1f}s)"
            )
            print(f"[smoke] Project preserved at {tmp_root}")
            if warnings:
                for w in warnings:
                    print(f"[smoke] WARN — {w}")
            return 0
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="End-to-end smoke for the dress-rehearsal Phase 4."
    )
    parser.add_argument(
        "--scenario",
        choices=["5a", "5b", "5c"],
        default="5a",
        help=(
            "5a: happy-path rehearsal on shakedown fixture (default). "
            "5b: deliberate selector break — expect BLOCKED with "
            "FAIL_SELECTOR. "
            "5c: deliberate narration overclaim — expect narration "
            "regrounding or FAIL_NARRATIVE."
        ),
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(run_smoke(args.scenario)))
