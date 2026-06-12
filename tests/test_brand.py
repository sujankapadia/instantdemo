"""Tests for brand config + routes (M6).
Spec: tests/test-specs/test_brand.md."""

from __future__ import annotations

from pathlib import Path

import pytest

from instantdemo import brand

# Smallest valid PNG (1x1 transparent pixel).
PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


class TestConfig:
    def test_defaults(self, tmp_path: Path):  # BR1
        assert brand.load(tmp_path) is None
        config = brand.load_or_default(tmp_path)
        assert config.logo is None
        assert config.outro_enabled is False

    def test_round_trip(self, tmp_path: Path):  # BR2
        brand.save(tmp_path, brand.BrandConfig(
            logo=".instantdemo/logo.png", outro_enabled=True,
            outro_text="Thanks for watching", outro_duration_s=6.0,
        ))
        loaded = brand.load(tmp_path)
        assert loaded is not None
        assert loaded.logo == ".instantdemo/logo.png"
        assert loaded.outro_enabled is True
        assert loaded.outro_text == "Thanks for watching"
        assert loaded.outro_duration_s == 6.0

    def test_dangling_logo(self, tmp_path: Path):  # BR3
        config = brand.BrandConfig(logo=".instantdemo/gone.png")
        assert brand.resolve_logo(tmp_path, config) is None


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("INSTANTDEMO_PROJECT_DIR", str(tmp_path))
    (tmp_path / ".instantdemo").mkdir()
    from fastapi.testclient import TestClient
    from instantdemo.server.app import create_app

    with TestClient(create_app()) as c:
        yield tmp_path, c


class TestRoutes:
    def test_upload_valid_png(self, client):  # BR4
        project, c = client
        res = c.post(
            "/api/project/brand/logo",
            files={"file": ("logo.png", PNG_BYTES, "image/png")},
        )
        assert res.status_code == 200, res.text
        assert res.json()["logo_exists"] is True
        assert (project / ".instantdemo" / "logo.png").read_bytes() == PNG_BYTES

    def test_upload_rejections(self, client):  # BR5
        _, c = client
        res = c.post(
            "/api/project/brand/logo",
            files={"file": ("logo.svg", b"<svg/>", "image/svg+xml")},
        )
        assert res.status_code == 422
        res = c.post(
            "/api/project/brand/logo",
            files={"file": ("big.png", b"x" * (2 * 1024 * 1024 + 1), "image/png")},
        )
        assert res.status_code == 422
        res = c.post(
            "/api/project/brand/logo",
            files={"file": ("empty.png", b"", "image/png")},
        )
        assert res.status_code == 422

    def test_put_outro(self, client):  # BR6
        project, c = client
        res = c.put("/api/project/brand", json={
            "outro_enabled": True, "outro_text": "Try it yourself",
            "outro_duration_s": 5.0,
        })
        assert res.status_code == 200
        saved = brand.load(project)
        assert saved is not None and saved.outro_enabled is True
        assert saved.outro_text == "Try it yourself"
        res = c.put("/api/project/brand", json={
            "outro_enabled": True, "outro_text": "x",
            "outro_duration_s": 60.0,
        })
        assert res.status_code == 422  # clamped by validation

    def test_delete_logo_route(self, client):  # BR7
        project, c = client
        c.post(
            "/api/project/brand/logo",
            files={"file": ("logo.png", PNG_BYTES, "image/png")},
        )
        res = c.delete("/api/project/brand/logo")
        assert res.status_code == 200
        assert res.json()["logo_exists"] is False
        assert not (project / ".instantdemo" / "logo.png").exists()


class TestOutroTiming:
    def test_timing_writer_outro(self, tmp_path: Path):  # OT1
        import json
        from instantdemo.render import BREATH_S, _write_segment_timing

        state_dir = tmp_path / ".instantdemo"
        segments = [
            {"action": "wait", "narration": "Hi.", "pause_after_ms": 0},
        ]
        _write_segment_timing(
            state_dir, segments, [2.0], "demo.mp4", outro_s=4.0
        )
        t = json.loads((state_dir / "segment-timing.json").read_text())
        assert t["outro_s"] == 4.0
        assert len(t["segments"]) == 1  # no outro row
        assert t["total_duration_s"] == round(2.0 + BREATH_S + 4.0, 3)
        srt = (tmp_path / "demo.srt").read_text()
        assert srt.count("-->") == 1  # no outro cue

    def test_rebuild_carries_outro(self):  # OT2
        from instantdemo.render import rebuild_section_timing

        old = {
            "outro_s": 4.0,
            "segments": [
                {"index": i, "start_s": i * 5.0, "end_s": (i + 1) * 5.0,
                 "audio_duration_s": 4.0, "recorded_clean_duration_s": 5.0}
                for i in range(3)
            ],
        }
        out = rebuild_section_timing(
            old, [{}] * 3, start_idx=1, end_idx=1, old_chapter_len=1,
            section_slots_s=[5.0], section_recorded_s=[5.0],
            section_audio_s=[4.0], output_filename="demo.mp4",
        )
        assert out["outro_s"] == 4.0
        assert out["total_duration_s"] == 15.0 + 4.0

    def test_load_outro_s(self, tmp_path: Path):  # OT3
        import json
        from instantdemo.server.routes.segments import _load_outro_s

        state_dir = tmp_path / ".instantdemo"
        state_dir.mkdir()
        assert _load_outro_s(state_dir) == 0.0
        (state_dir / "segment-timing.json").write_text("{bad")
        assert _load_outro_s(state_dir) == 0.0
        (state_dir / "segment-timing.json").write_text(
            json.dumps({"outro_s": 3.5, "segments": []})
        )
        assert _load_outro_s(state_dir) == 3.5
