"""Unit tests for the rehearsal progress log (M8/#85 item 3).
Spec: tests/test-specs/test_rehearsal_progress.md."""

from __future__ import annotations

import asyncio
from pathlib import Path

from instantdemo.phases.analyze import parse_progress_line, tail_progress_log
from instantdemo.phases.explore import _build_initial_prompt
from instantdemo import storyboard


def test_parse_setup_line():  # P1
    assert parse_progress_line("setup 3/7") == {
        "kind": "setup",
        "current": 3,
        "total": 7,
    }


def test_parse_scene_line():  # P2
    assert parse_progress_line("scene s12") == {
        "kind": "scene",
        "scene_id": "s12",
    }


def test_malformed_lines_return_none():  # P3
    for bad in ("", "setup x/y", "banana", "setup 3/0", "scene", "scene 12"):
        assert parse_progress_line(bad) is None, bad


def _drain(path: Path, *, polls: int = 3) -> list[dict]:
    """Run the tailer for a few poll intervals, collecting emits."""
    events: list[dict] = []

    async def scenario():
        task = asyncio.create_task(
            tail_progress_log(path, events.append, interval=0.01)
        )
        await asyncio.sleep(0.01 * polls)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(scenario())
    return events


def test_split_write_buffers_partial_line(tmp_path):  # P4
    log = tmp_path / "progress.log"

    async def scenario():
        events: list[dict] = []
        task = asyncio.create_task(
            tail_progress_log(log, events.append, interval=0.01)
        )
        # First chunk ends mid-line (no newline after "scene s2").
        log.write_text("setup 1/2\nscene s")
        await asyncio.sleep(0.05)
        # Second chunk completes the line and adds another.
        with log.open("a") as fh:
            fh.write("2\nscene s3\n")
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return events

    events = asyncio.run(scenario())
    assert events == [
        {"type": "rehearsal_progress", "phase": 4, "kind": "setup",
         "current": 1, "total": 2},
        {"type": "rehearsal_progress", "phase": 4, "kind": "scene",
         "scene_id": "s2"},
        {"type": "rehearsal_progress", "phase": 4, "kind": "scene",
         "scene_id": "s3"},
    ]


def test_absent_file_no_crash(tmp_path):  # P5
    events = _drain(tmp_path / "never.log", polls=3)
    assert events == []


def test_truncation_resets_offset(tmp_path):  # P6
    log = tmp_path / "progress.log"

    async def scenario():
        events: list[dict] = []
        task = asyncio.create_task(
            tail_progress_log(log, events.append, interval=0.01)
        )
        log.write_text("scene s10\nscene s11\n")
        await asyncio.sleep(0.05)
        # A fresh iteration truncates and writes anew (genuinely
        # smaller — the offset must reset, not skip past the new line).
        log.write_text("scene s2\n")
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return events

    events = asyncio.run(scenario())
    ids = [e["scene_id"] for e in events if e["kind"] == "scene"]
    assert ids == ["s10", "s11", "s2"]


def test_prompt_carries_progress_contract(tmp_path):  # P7
    doc = storyboard.new_document(title="Tour", url="http://x/")
    for ch, n in (("Intro", 2), ("Body", 2)):
        for _ in range(n):
            storyboard.add_scene(
                doc, title="t", narration="x", action="wait", section=ch,
            )
    shots = tmp_path / "rehearsal"
    # Scoped revision of the SECOND chapter → a non-empty prefix.
    scoped = _build_initial_prompt(
        doc, "http://x/", "phase3.md", shots, section="Body",
    )
    assert "progress.log" in scoped
    assert "setup k/" in scoped
    # The per-scene contract rides in the phase4 template.
    assert "scene <scene_id>" in scoped
