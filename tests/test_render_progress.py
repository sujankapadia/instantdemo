"""Unit tests for render progress events (M8/#85 item 1).
Spec: tests/test-specs/test_render_progress.md."""

from __future__ import annotations

import asyncio
from pathlib import Path

from instantdemo.phases.render import _invoke_renderer, _progress_emitter
from instantdemo.render import generate_audio, ResolvedTTS


def test_emitter_thread_safe_delivery():  # RP1
    async def scenario():
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        on_progress = _progress_emitter(loop, queue.put_nowait)
        # Fire from a worker thread, exactly like the renderer does.
        await loop.run_in_executor(
            None, on_progress, "recording", 3, 12
        )
        return await asyncio.wait_for(queue.get(), timeout=5)

    event = asyncio.run(scenario())
    assert event == {
        "type": "render_progress",
        "phase": 6,
        "stage": "recording",
        "current": 3,
        "total": 12,
    }


def test_no_emitter_means_none():  # RP2
    loop = object()  # never touched when emit is None
    assert _progress_emitter(loop, None) is None


class FakeContext:
    """Just enough Context for _invoke_renderer's two paths."""

    def __init__(self, tmp_path: Path):
        self.script_path = tmp_path / "demo-script.json"
        self.output = tmp_path / "demo.mp4"
        self.state_dir = tmp_path / ".instantdemo"
        self.project = tmp_path
        self.tts = None
        self.section_scope = None


def test_full_render_path_threads_callback(tmp_path, monkeypatch):  # RP3
    from instantdemo.phases import render as phase_render

    received = {}
    monkeypatch.setattr(
        phase_render, "_section_render_plan", lambda c: None
    )
    monkeypatch.setattr(
        phase_render, "render_main",
        lambda argv, *, on_progress=None: received.update(
            cb=on_progress
        ),
    )
    sentinel = lambda *a: None  # noqa: E731
    _invoke_renderer(FakeContext(tmp_path), sentinel)
    assert received["cb"] is sentinel


def test_section_path_threads_callback(tmp_path, monkeypatch):  # RP4
    from instantdemo.phases import render as phase_render

    received = {}
    monkeypatch.setattr(
        phase_render, "_section_render_plan", lambda c: (2, 4, 3)
    )

    def fake_section(*args, **kwargs):
        received["cb"] = kwargs.get("on_progress")

    monkeypatch.setattr(phase_render, "render_section_main", fake_section)
    sentinel = lambda *a: None  # noqa: E731
    ctx = FakeContext(tmp_path)
    ctx.section_scope = "Some chapter"
    _invoke_renderer(ctx, sentinel)
    assert received["cb"] is sentinel


def test_dispatcher_passes_on_progress(tmp_path, monkeypatch):  # RP5
    from instantdemo import render as render_mod

    received = {}

    def fake_pocket(segments, tmp_dir, voice, ref, *, on_progress=None):
        received["cb"] = on_progress
        return []

    monkeypatch.setattr(
        render_mod, "generate_audio_pocket_tts", fake_pocket
    )
    sentinel = lambda *a: None  # noqa: E731
    generate_audio(
        [], tmp_path, ResolvedTTS(), tmp_path / ".env",
        on_progress=sentinel,
    )
    assert received["cb"] is sentinel


def test_provider_loop_emits_in_order(tmp_path):  # RP6
    # The provider-loop contract, exercised against the same loop shape
    # all five providers share: report (narrating, i+1, N) at the top
    # of each iteration, including empty-narration segments.
    events = []

    def on_progress(stage, current, total):
        events.append((stage, current, total))

    segments = [{"narration": t} for t in ("one", "", "three")]
    for i, seg in enumerate(segments):
        if on_progress is not None:
            on_progress("narrating", i + 1, len(segments))
    assert events == [
        ("narrating", 1, 3),
        ("narrating", 2, 3),
        ("narrating", 3, 3),
    ]
