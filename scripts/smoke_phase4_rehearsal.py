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

import asyncio
import json
import os
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


async def run_smoke() -> int:
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

    tmp_root = Path(tempfile.mkdtemp(prefix="instantdemo-smoke-phase4-"))
    # Copy fixture contents (including .instantdemo/) to tmp_root.
    for entry in FIXTURE.iterdir():
        dest = tmp_root / entry.name
        if entry.is_dir():
            shutil.copytree(entry, dest)
        else:
            shutil.copy2(entry, dest)
    state_dir = tmp_root / ".instantdemo"

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

            for required in ("phase_started", "phase_complete", "run_complete"):
                if required not in event_types:
                    errors.append(f"missing event: {required}")

            state_path = state_dir / "state.json"
            if not state_path.exists():
                errors.append("state.json was not created")
            else:
                state = json.loads(state_path.read_text())
                phase4 = (state.get("phases") or {}).get("4") or {}
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
                cost = phase4.get("cost_usd") or 0
                if cost <= 0:
                    errors.append(
                        f"phases.4.cost_usd expected > 0, got {cost}"
                    )
                elif cost > 0.50:
                    warnings.append(
                        f"phases.4.cost_usd ${cost:.4f} exceeds the "
                        "$0.50 ceiling for single-pass rehearsal"
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

            print(
                f"[smoke] PASS  — phase 4 OK "
                f"({summary.get('pass', '?')}/{summary.get('total', '?')} PASS, "
                f"{n_swaps} selector swaps, "
                f"{n_regrnd} narration regroundings) "
                f"(${cost:.4f}, {duration_ms / 1000:.1f}s)"
            )
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
    sys.exit(asyncio.run(run_smoke()))
