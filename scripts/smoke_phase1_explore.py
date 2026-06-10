#!/usr/bin/env python3
"""End-to-end smoke for the explore-first Phase 1 (M1).

Self-contained: serves a tiny 3-page static site with stdlib
http.server as the "app under demo" (no dependency on the Evernote /
cca fixture apps), spawns `instantdemo serve` on a temp project, and
exercises the M1 surface:

  1. POST /api/preflight — ok + title + screenshot served
  2. POST /api/runs {phases:[1], docs, intent.goal} — SSE stream must
     carry >=1 `screenshot` event; run completes
  3. state.json: phases.1.intent_proposal.goal non-empty;
     intent_confirmed == false; exploration dir non-empty and listed
     by GET /api/project/exploration; phase1.md ANSWER block parses
  4. (--confirm) POST {phases:[2], intent} — intent_confirmed flips
     true (costs ~$0.05 more; default off)

Cost: ~$0.15-0.25 (Phase 1 on a 3-page static site).
Exit codes: 0 pass, 1 fail.
"""

from __future__ import annotations

import argparse
import asyncio
import http.server
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from functools import partial
from pathlib import Path

import httpx

PAGES = {
    "index.html": """<!doctype html><html><head><title>Snackboard — Team Snack Voting</title></head>
<body><h1>Snackboard</h1><p>Vote on snacks for the office.</p>
<nav><a href="snacks.html">Snacks</a> <a href="results.html">Results</a></nav>
<ul><li>Pretzels</li><li>Mango strips</li><li>Dark chocolate</li></ul></body></html>""",
    "snacks.html": """<!doctype html><html><head><title>Snacks — Snackboard</title></head>
<body><h1>All snacks</h1><nav><a href="index.html">Home</a> <a href="results.html">Results</a></nav>
<table><tr><th>Snack</th><th>Votes</th></tr><tr><td>Pretzels</td><td>12</td></tr>
<tr><td>Mango strips</td><td>9</td></tr><tr><td>Dark chocolate</td><td>17</td></tr></table></body></html>""",
    "results.html": """<!doctype html><html><head><title>Results — Snackboard</title></head>
<body><h1>This week's winner</h1><nav><a href="index.html">Home</a></nav>
<p>Dark chocolate wins with 17 votes.</p></body></html>""",
}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_fixture_site() -> tuple[str, http.server.ThreadingHTTPServer]:
    site_dir = Path(tempfile.mkdtemp(prefix="snackboard-"))
    for name, html in PAGES.items():
        (site_dir / name).write_text(html)
    handler = partial(
        http.server.SimpleHTTPRequestHandler, directory=str(site_dir)
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_port}/", server


def wait_for_health(base_url: str, timeout_s: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{base_url}/api/health", timeout=1).status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    return False


async def run_smoke(confirm: bool) -> int:
    app_url, site = start_fixture_site()
    project = Path(tempfile.mkdtemp(prefix="instantdemo-smoke-m1-"))
    state_dir = project / ".instantdemo"
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    print(f"[smoke] Fixture app: {app_url}")
    print(f"[smoke] Project:     {project}")

    server = subprocess.Popen(
        ["instantdemo", "serve", "--project", str(project),
         "--port", str(port), "--no-open"],
        env=os.environ.copy(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        if not wait_for_health(base):
            print("[smoke] FAIL: server not healthy", file=sys.stderr)
            return 1

        errors: list[str] = []
        async with httpx.AsyncClient(base_url=base, timeout=900) as client:
            # 1. Pre-flight
            pf = (await client.post(
                "/api/preflight", json={"url": app_url}
            )).json()
            if not pf.get("ok"):
                errors.append(f"preflight not ok: {pf}")
            if "Snackboard" not in (pf.get("title") or ""):
                errors.append(f"preflight title: {pf.get('title')!r}")
            shot = await client.get("/api/preflight/screenshot")
            if shot.status_code != 200:
                errors.append(f"preflight screenshot: {shot.status_code}")

            # 2. Exploration run
            resp = await client.post("/api/runs", json={
                "phases": [1],
                "url": app_url,
                "docs": "Snackboard is a lightweight team snack-voting "
                        "board. Pages: home, all snacks, weekly results.",
                "intent": {"goal": "Show how the team sees this week's "
                                   "winning snack"},
            })
            if resp.status_code != 202:
                print(f"[smoke] FAIL: POST /api/runs {resp.status_code}: "
                      f"{resp.text}", file=sys.stderr)
                return 1
            run_id = resp.json()["run_id"]

            screenshot_events = 0
            terminal = None
            async with client.stream(
                "GET", f"/api/runs/{run_id}/stream"
            ) as stream:
                async for line in stream.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    try:
                        event = json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue
                    if event.get("type") == "screenshot":
                        screenshot_events += 1
                    if event.get("type") in (
                        "run_complete", "run_canceled", "run_error"
                    ):
                        terminal = event["type"]
                        break

            if terminal != "run_complete":
                errors.append(f"terminal event: {terminal}")
            if screenshot_events < 1:
                errors.append("no screenshot SSE events")

            # 3. Post-run assertions
            state = json.loads((state_dir / "state.json").read_text())
            phase1 = (state.get("phases") or {}).get("1") or {}
            proposal = phase1.get("intent_proposal") or {}
            if not proposal.get("goal"):
                errors.append("intent_proposal.goal missing")
            if state.get("intent_confirmed") is not False:
                errors.append(
                    f"intent_confirmed: {state.get('intent_confirmed')!r}"
                )
            listing = (await client.get("/api/project/exploration")).json()
            if not listing.get("files"):
                errors.append("exploration listing empty")
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
            from instantdemo.checkpoints import parse_answer_block
            answers = parse_answer_block(
                (state_dir / "phase1.md").read_text()
            )
            if not answers.get("flow"):
                errors.append("phase1.md ANSWER block missing flow")
            if not (project / "product-context.md").exists():
                errors.append("product-context.md not written")

            # 4. Optional: confirm flips the marker
            if confirm and not errors:
                resp = await client.post("/api/runs", json={
                    "phases": [2],
                    "url": app_url,
                    "intent": proposal,
                })
                run_id = resp.json()["run_id"]
                async with client.stream(
                    "GET", f"/api/runs/{run_id}/stream"
                ) as stream:
                    async for line in stream.aiter_lines():
                        if line.startswith("data: ") and any(
                            t in line for t in
                            ("run_complete", "run_error", "run_canceled")
                        ):
                            break
                state = json.loads((state_dir / "state.json").read_text())
                if state.get("intent_confirmed") is not True:
                    errors.append("intent_confirmed did not flip true")

        if errors:
            print("[smoke] FAIL:", file=sys.stderr)
            for err in errors:
                print(f"  - {err}", file=sys.stderr)
            return 1

        cost = phase1.get("cost_usd") or 0
        print(
            f"[smoke] PASS — phase 1 explored the fixture site "
            f"({screenshot_events} screenshot events, "
            f"{len(listing['files'])} files, ${cost:.4f}); "
            f"proposal: {proposal.get('goal', '')[:60]}..."
        )
        return 0
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
        site.shutdown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm", action="store_true",
        help="also run phases [2] with the proposal to verify the "
             "intent_confirmed flip (~$0.05 extra)",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(run_smoke(args.confirm)))
