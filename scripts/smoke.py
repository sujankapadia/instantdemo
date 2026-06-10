#!/usr/bin/env python3
"""End-to-end smoke check for the InstantDemo GUI run pipeline.

Spawns a temporary `instantdemo serve` against a synthetic minimal
project, kicks off a Phase 2 run via the API, watches the SSE stream
through to completion, and asserts the run succeeded.

Cost: roughly $0.04 in Claude usage per invocation (~30s wall time).
Requires:
    - instantdemo[gui,dev] installed (the dev extra brings in httpx)
    - `claude` CLI authenticated (or ANTHROPIC_API_KEY with credit)

Exit code:
    0  smoke pass
    1  smoke fail

Run manually before tagging a release, or whenever the run pipeline
changes shape (Pydantic models, SSE event types, state.json schema).
A future iteration will promote this into a pytest-based suite.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx


PHASE1_FIXTURE = """\
<!-- ANSWER THESE BEFORE CONTINUING -->
flow: smoke check demo
url: http://example.test
seed_data_ready: yes
<!-- /ANSWER -->

## Smoke Check App Overview

This is a synthetic placeholder for the InstantDemo end-to-end smoke
check. It exercises the Phase 2 narration pipeline with a minimal
upstream artifact.

### Main screens

- `/` — landing page
- `/about` — secondary page

### Notes

The Phase 2 agent will produce a narrative plan based on this minimal
context. Output content isn't checked for quality — only that the
pipeline emits the right SSE events and persists the run to state.json.
"""


def find_free_port() -> int:
    """Bind to port 0, return whatever the OS assigned."""
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


async def run_smoke() -> int:
    tmp_root = Path(tempfile.mkdtemp(prefix="instantdemo-smoke-"))
    state_dir = tmp_root / ".instantdemo"
    state_dir.mkdir()
    (state_dir / "phase1.md").write_text(PHASE1_FIXTURE)

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

    print("[smoke] Server ready. Starting Phase 2 run.")

    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=180.0) as client:
            resp = await client.post(
                "/api/runs",
                json={"phases": [2], "url": "http://example.test"},
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

            print(f"[smoke] Events:  {event_types}")

            errors: list[str] = []
            for required in ("phase_started", "phase_complete", "run_complete"):
                if required not in event_types:
                    errors.append(f"missing event: {required}")

            state_path = state_dir / "state.json"
            if not state_path.exists():
                errors.append("state.json was not created")
            else:
                state = json.loads(state_path.read_text())
                phase2 = (state.get("phases") or {}).get("2") or {}
                if phase2.get("status") != "completed":
                    errors.append(
                        f"phases.2.status expected 'completed', got "
                        f"{phase2.get('status')!r}"
                    )
                cost = phase2.get("cost_usd") or 0
                if cost <= 0:
                    errors.append(
                        f"phases.2.cost_usd expected > 0, got {cost}"
                    )
                if state.get("current_run_id") is not None:
                    errors.append(
                        "current_run_id should be cleared after completion, "
                        f"got {state.get('current_run_id')!r}"
                    )

            video_path = tmp_root / "demo.mp4"
            if video_path.exists():
                errors.append(
                    "demo.mp4 should not exist after a Phase-2-only run"
                )

            # Storyboard contract (M0): Phase 2 must create the
            # canonical structured artifact plus its rendered view.
            sb_path = state_dir / "storyboard.json"
            if not sb_path.exists():
                errors.append("storyboard.json was not created")
            else:
                sb = json.loads(sb_path.read_text())
                if sb.get("version") != 1:
                    errors.append(
                        f"storyboard version expected 1, got {sb.get('version')!r}"
                    )
                scenes = sb.get("scenes") or []
                if not scenes:
                    errors.append("storyboard has no scenes")
                for i, scene in enumerate(scenes, start=1):
                    for field in ("id", "title", "action"):
                        if not scene.get(field):
                            errors.append(
                                f"storyboard scene {i} missing {field!r}"
                            )
            view_path = state_dir / "phase2.md"
            if not view_path.exists():
                errors.append("phase2.md view was not created")
            elif "### Segment 1" not in view_path.read_text():
                errors.append(
                    "phase2.md view missing '### Segment 1' heading"
                )

            if errors:
                print("[smoke] FAIL:", file=sys.stderr)
                for err in errors:
                    print(f"  - {err}", file=sys.stderr)
                return 1

            phase2_data = (
                json.loads(state_path.read_text())["phases"]["2"]
            )
            cost = phase2_data["cost_usd"]
            duration_s = (phase2_data.get("duration_ms") or 0) / 1000
            print(
                f"[smoke] PASS  — phase 2 completed "
                f"(${cost:.4f}, {duration_s:.1f}s)"
            )
            return 0
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    sys.exit(asyncio.run(run_smoke()))
