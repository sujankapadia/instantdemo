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

    def test_delete_logo(self, client):  # BR7
        project, c = client
        c.post(
            "/api/project/brand/logo",
            files={"file": ("logo.png", PNG_BYTES, "image/png")},
        )
        res = c.delete("/api/project/brand/logo")
        assert res.status_code == 200
        assert res.json()["logo_exists"] is False
        assert not (project / ".instantdemo" / "logo.png").exists()
