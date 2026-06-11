"""Route tests for the takes API (M4).
Spec: tests/test-specs/test_takes_routes.md."""

from __future__ import annotations

from pathlib import Path

import pytest

from instantdemo import takes


def make_project(tmp_path: Path) -> Path:
    (tmp_path / ".instantdemo").mkdir(exist_ok=True)
    (tmp_path / "demo.mp4").write_bytes(b"FILM-v0")
    (tmp_path / "demo-script.json").write_text('{"segments": []}')
    return tmp_path


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("INSTANTDEMO_PROJECT_DIR", str(tmp_path))
    make_project(tmp_path)
    from fastapi.testclient import TestClient
    from instantdemo.server.app import create_app

    with TestClient(create_app()) as c:
        yield tmp_path, c


class TestTakesRoutes:
    def test_list(self, client):  # R1
        project, c = client
        takes.snapshot(project, "render")
        (project / "demo.mp4").write_bytes(b"FILM-v1")
        takes.snapshot(project, "re-record")
        body = c.get("/api/project/takes").json()
        assert [t["n"] for t in body["takes"]] == [2, 1]
        assert body["takes"][0]["label"] == "re-record"
        assert body["takes"][0]["video_exists"] is True

    def test_video(self, client):  # R2
        project, c = client
        takes.snapshot(project, "render")
        res = c.get("/api/project/takes/1/video")
        assert res.status_code == 200
        assert res.headers["content-type"] == "video/mp4"
        assert res.content == b"FILM-v0"

    def test_video_missing(self, client):  # R3
        _, c = client
        assert c.get("/api/project/takes/9/video").status_code == 404

    def test_restore(self, client):  # R4
        project, c = client
        takes.snapshot(project, "render")
        (project / "demo.mp4").write_bytes(b"FILM-v1")
        res = c.post("/api/project/takes/1/restore")
        assert res.status_code == 200
        assert (project / "demo.mp4").read_bytes() == b"FILM-v0"
        assert "takes" in res.json()

    def test_restore_during_run(self, client):  # R5
        project, c = client
        takes.snapshot(project, "render")

        class FakeRun:
            status = "running"

        c.app.state.run_manager.active = FakeRun()
        try:
            assert c.post("/api/project/takes/1/restore").status_code == 409
        finally:
            c.app.state.run_manager.active = None

    def test_restore_pruned(self, client):  # R6
        project, c = client
        for i in range(5):
            takes.snapshot(project, f"t{i}")
        res = c.post("/api/project/takes/1/restore")
        assert res.status_code == 409
        assert "pruned" in res.json()["detail"]
