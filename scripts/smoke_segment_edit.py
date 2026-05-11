#!/usr/bin/env python3
"""Smoke check for the segment-edit + audio re-render path.

Copies the gitignored baseline fixture into a tmp project, spins up
`instantdemo serve` against it, PATCHes a segment's narration, then
hits the audio re-render endpoint and asserts that demo.mp4 was
updated in place and segment-timing.json was written.

Costs nothing (no agent calls). Requires Kokoro TTS to be installed
locally, since the re-render endpoint regenerates all segment audio
via Kokoro. Wall time: ~50s for the fixture's 15 segments.

Exit code:
    0  smoke pass
    1  smoke fail (missing fixture, server hang, endpoint failure,
       unchanged demo.mp4, missing segment-timing.json)

Run manually before tagging a release, or whenever segments.py /
render.py change shape.
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


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = (
    REPO_ROOT / "fixtures" / "baseline-claude-code-analytics-2026-05-01"
)


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


async def run_smoke() -> int:
    if not FIXTURE_DIR.exists():
        print(
            f"[smoke] FAIL: fixture not found at {FIXTURE_DIR}",
            file=sys.stderr,
        )
        print(
            "[smoke] (the baseline fixture is gitignored — restore it "
            "from a previous skill run if missing)",
            file=sys.stderr,
        )
        return 1

    tmp_root = Path(tempfile.mkdtemp(prefix="instantdemo-segedit-"))
    for name in ("demo-script.json", "demo.mp4"):
        src = FIXTURE_DIR / name
        if not src.exists():
            print(f"[smoke] FAIL: fixture missing {name}", file=sys.stderr)
            return 1
        shutil.copy2(src, tmp_root / name)

    original_video_mtime = (tmp_root / "demo.mp4").stat().st_mtime

    # Seed segment-timing.json with synthetic recorded_clean_duration_s
    # values to verify the audio re-render preserves them (#19). The
    # rendered fixture predates #19, so the file doesn't carry these
    # fields naturally; we inject them here to exercise the round-trip.
    fixture_script = json.loads(
        (tmp_root / "demo-script.json").read_text()
    )
    n_segments = len(fixture_script["segments"])
    # Use deliberately small recorded durations so all segments overflow
    # after re-render (Kokoro narrations run ~3s per segment, well past
    # 0.5s). Lets us assert the overflow detection wired through #19
    # surfaces correctly.
    seeded_durations = [
        round(0.5 + 0.05 * i, 3) for i in range(n_segments)
    ]
    (tmp_root / ".instantdemo").mkdir(parents=True, exist_ok=True)
    (tmp_root / ".instantdemo" / "segment-timing.json").write_text(
        json.dumps(
            {
                "video": "demo.mp4",
                "total_duration_s": sum(seeded_durations),
                "segments": [
                    {
                        "index": i,
                        "start_s": 0.0,
                        "end_s": seeded_durations[i],
                        "audio_duration_s": seeded_durations[i],
                        "recorded_clean_duration_s": seeded_durations[i],
                    }
                    for i in range(n_segments)
                ],
            },
            indent=2,
        )
        + "\n"
    )

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

    print("[smoke] Server ready.")

    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=300.0) as client:
            errors: list[str] = []

            # Verify segments endpoint sees the fixture.
            r = await client.get("/api/project/segments")
            if r.status_code != 200:
                errors.append(
                    f"GET /api/project/segments returned {r.status_code}"
                )
            else:
                payload = r.json()
                if not payload.get("exists"):
                    errors.append("segments.exists was false")
                segs = payload.get("segments") or []
                if len(segs) < 1:
                    errors.append("segments list was empty")

            new_narration = "Smoke test narration override."
            r = await client.patch(
                "/api/segments/0",
                json={"narration": new_narration},
            )
            if r.status_code != 200:
                errors.append(
                    f"PATCH /api/segments/0 returned {r.status_code}: {r.text}"
                )
            elif r.json().get("narration") != new_narration:
                errors.append(
                    "PATCH response did not echo the new narration"
                )

            # Verify the change persisted to demo-script.json.
            script = json.loads((tmp_root / "demo-script.json").read_text())
            if script["segments"][0].get("narration") != new_narration:
                errors.append(
                    "demo-script.json did not reflect the patched narration"
                )

            print("[smoke] PATCH ok. Re-rendering audio (Kokoro)…")
            t0 = time.monotonic()
            r = await client.post("/api/segments/0/re-render-audio")
            elapsed = time.monotonic() - t0
            if r.status_code != 200:
                errors.append(
                    f"POST re-render-audio returned {r.status_code}: {r.text}"
                )
            else:
                result = r.json()
                if not result.get("ok"):
                    errors.append(f"re-render result.ok was false: {result}")
                if (result.get("new_audio_duration_ms") or 0) <= 0:
                    errors.append(
                        f"new_audio_duration_ms was non-positive: {result}"
                    )
                # Post-#37: when recorded_durations are present, the
                # re-render extends each overflowing segment's video
                # (tpad) so audio plays in full without bleed. So
                # overflow now means "we couldn't extend" — should
                # be false here since durations are seeded.
                if result.get("overflow"):
                    errors.append(
                        f"re-render result.overflow expected false (per-segment "
                        f"extension should have handled it), got "
                        f"{result.get('overflow')!r}"
                    )

            # GET /api/project/segments should now surface audio_overflows
            # on the edited segment (server-side join of audio vs recorded
            # durations).
            r = await client.get("/api/project/segments")
            if r.status_code == 200:
                payload = r.json()
                seg0 = (payload.get("segments") or [None])[0]
                if seg0 is None:
                    errors.append("segments[0] missing in second fetch")
                elif not seg0.get("audio_overflows"):
                    errors.append(
                        f"segments[0].audio_overflows expected true, got "
                        f"{seg0.get('audio_overflows')!r}"
                    )

            new_video_mtime = (tmp_root / "demo.mp4").stat().st_mtime
            if new_video_mtime <= original_video_mtime:
                errors.append(
                    "demo.mp4 mtime did not advance — video was not rewritten"
                )

            # DELETE the last segment and verify the script + timing shrink.
            initial_count = len(fixture_script["segments"])
            target_index = initial_count - 1
            print(f"[smoke] Deleting segment {target_index} (frame-accurate cut)…")
            t1 = time.monotonic()
            r = await client.delete(f"/api/segments/{target_index}")
            delete_elapsed = time.monotonic() - t1
            if r.status_code != 200:
                errors.append(
                    f"DELETE /api/segments/{target_index} returned "
                    f"{r.status_code}: {r.text}"
                )
            else:
                result = r.json()
                if result.get("remaining_segments") != initial_count - 1:
                    errors.append(
                        f"delete remaining_segments expected "
                        f"{initial_count - 1}, got "
                        f"{result.get('remaining_segments')}"
                    )

            post_delete_script = json.loads(
                (tmp_root / "demo-script.json").read_text()
            )
            if len(post_delete_script["segments"]) != initial_count - 1:
                errors.append(
                    f"demo-script.json segment count expected "
                    f"{initial_count - 1}, got "
                    f"{len(post_delete_script['segments'])}"
                )

            timing_path = tmp_root / ".instantdemo" / "segment-timing.json"
            if not timing_path.exists():
                errors.append(
                    f"segment-timing.json was not written at {timing_path}"
                )
            else:
                timing = json.loads(timing_path.read_text())
                timing_segs = timing.get("segments") or []
                if not timing_segs:
                    errors.append("segment-timing.json had no segments")
                else:
                    # Verify recorded_clean_duration_s survived the re-render
                    # (issue #19 preservation contract).
                    for i, seg in enumerate(timing_segs):
                        actual = seg.get("recorded_clean_duration_s")
                        expected = seeded_durations[i]
                        if actual != expected:
                            errors.append(
                                f"segment {i} recorded_clean_duration_s "
                                f"expected {expected}, got {actual!r}"
                            )
                            break

            if errors:
                print("[smoke] FAIL:", file=sys.stderr)
                for err in errors:
                    print(f"  - {err}", file=sys.stderr)
                return 1

            print(
                f"[smoke] PASS  — edit ({elapsed:.1f}s) + delete "
                f"({delete_elapsed:.1f}s)"
            )
            return 0
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
        shutil.rmtree(tmp_root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(asyncio.run(run_smoke()))
