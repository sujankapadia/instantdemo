"""Tests for SRT captions (M6).
Spec: tests/test-specs/test_captions.md."""

from __future__ import annotations

from pathlib import Path

from instantdemo import takes
from instantdemo.captions import srt_text
from instantdemo.render import _write_segment_timing


def rows(*spans: tuple[float, float]) -> list[dict]:
    return [
        {"index": i, "start_s": a, "end_s": b}
        for i, (a, b) in enumerate(spans)
    ]


class TestSrtText:
    def test_silent_segment_skipped_renumbered(self):  # CP1
        segments = [
            {"narration": "First line."},
            {"narration": ""},
            {"narration": "Third line."},
        ]
        out = srt_text(segments, rows((0, 3), (3, 5), (5, 9)))
        blocks = out.strip().split("\n\n")
        assert len(blocks) == 2
        assert blocks[0].startswith("1\n00:00:00,000 --> 00:00:03,000")
        assert blocks[1].startswith("2\n00:00:05,000 --> 00:00:09,000")
        assert "Third line." in blocks[1]

    def test_timestamp_format(self):  # CP2
        out = srt_text(
            [{"narration": "x"}], rows((3661.5, 3700.042))
        )
        assert "01:01:01,500 --> 01:01:40,042" in out

    def test_display_text_verbatim(self):  # CP3
        out = srt_text(
            [{"narration": "Import your ENEX exports."}], rows((0, 2))
        )
        assert "Import your ENEX exports." in out

    def test_empty(self):  # CP4
        assert srt_text([], []) == ""


class TestHooks:
    def test_timing_write_emits_srt(self, tmp_path: Path):  # CP5
        state_dir = tmp_path / ".instantdemo"
        segments = [
            {"action": "wait", "narration": "Hello.", "pause_after_ms": 0},
            {"action": "wait", "narration": "", "pause_after_ms": 500},
        ]
        _write_segment_timing(state_dir, segments, [2.0, 1.0], "demo.mp4")
        srt = (tmp_path / "demo.srt").read_text()
        assert "Hello." in srt
        assert srt.count("-->") == 1  # silent segment has no cue

    def test_download_zip(self, tmp_path, monkeypatch):  # CP7
        import io
        import zipfile

        monkeypatch.setenv("INSTANTDEMO_PROJECT_DIR", str(tmp_path))
        (tmp_path / ".instantdemo").mkdir()
        from fastapi.testclient import TestClient
        from instantdemo.server.app import create_app

        with TestClient(create_app()) as c:
            assert c.get("/api/project/download").status_code == 404
            (tmp_path / "demo.mp4").write_bytes(b"FILM")
            res = c.get("/api/project/download")
            assert res.status_code == 200
            with zipfile.ZipFile(io.BytesIO(res.content)) as zf:
                assert zf.namelist() == ["demo.mp4"]
            (tmp_path / "demo.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nHi.\n")
            res = c.get("/api/project/download")
            with zipfile.ZipFile(io.BytesIO(res.content)) as zf:
                assert sorted(zf.namelist()) == ["demo.mp4", "demo.srt"]
                assert zf.read("demo.mp4") == b"FILM"

    def test_take_snapshot_carries_srt(self, tmp_path: Path):  # CP6
        (tmp_path / ".instantdemo").mkdir()
        (tmp_path / "demo.mp4").write_bytes(b"F")
        (tmp_path / "demo.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nHi.\n")
        n = takes.snapshot(tmp_path, "render")
        assert (takes.takes_dir(tmp_path) / f"v{n}" / "demo.srt").exists()
        (tmp_path / "demo.srt").write_text("CHANGED")
        takes.restore(tmp_path, n)
        assert "Hi." in (tmp_path / "demo.srt").read_text()
