"""Route tests for the storyboard API (M2).

Spec: tests/test-specs/test_storyboard_routes.md. Uses FastAPI's
TestClient with INSTANTDEMO_PROJECT_DIR pointed at a tmp project.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from instantdemo import state as state_mod
from instantdemo import storyboard


@pytest.fixture()
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A tmp project dir with a minimal verified storyboard +
    state.json, and a TestClient bound to it."""
    monkeypatch.setenv("INSTANTDEMO_PROJECT_DIR", str(tmp_path))
    state_dir = tmp_path / ".instantdemo"
    state_dir.mkdir()

    doc = storyboard.new_document(
        title="Test Demo", url="http://x/", summary="flow"
    )
    storyboard.add_scene(
        doc, title="Open", narration="Welcome.", action="goto",
        url="http://x/", wait_for=[".a"],
    )
    storyboard.add_scene(
        doc, title="Click", narration="Click it.", action="click",
        selector=[".b"],
    )
    for scene in doc["scenes"]:
        scene["status"] = "verified"
    storyboard.save(state_dir, doc)

    state_mod.record_phase_metrics(
        state_dir, 4,
        explore_findings={"summary": {"overall": "OK"}, "segments": []},
        explore_overall="OK",
    )

    from fastapi.testclient import TestClient
    from instantdemo.server.app import create_app

    # Context manager runs the lifespan, which creates
    # app.state.run_manager (needed by the 409 guard test).
    with TestClient(create_app()) as client:
        yield tmp_path, state_dir, client


class TestGetStoryboard:
    def test_round_trip(self, project):  # SG1
        _, _, client = project
        body = client.get("/api/project/storyboard").json()
        assert body["exists"] is True
        scenes = body["storyboard"]["scenes"]
        assert [s["id"] for s in scenes] == ["s1", "s2"]
        assert scenes[0]["status"] == "verified"

    def test_absent_doc(self, tmp_path, monkeypatch):  # SG2
        monkeypatch.setenv("INSTANTDEMO_PROJECT_DIR", str(tmp_path))
        from fastapi.testclient import TestClient
        from instantdemo.server.app import create_app

        res = TestClient(create_app()).get("/api/project/storyboard")
        assert res.status_code == 200
        assert res.json() == {"exists": False, "storyboard": None}


class TestPatchScene:
    def test_edit_updates_doc_and_revision(self, project):  # SP1
        _, state_dir, client = project
        before = json.loads(
            storyboard.path_for(state_dir).read_text()
        )["updated_at"]
        res = client.patch(
            "/api/project/storyboard/scenes/s1",
            json={"narration": "Hello there."},
        )
        assert res.status_code == 200
        doc = json.loads(storyboard.path_for(state_dir).read_text())
        scene = doc["scenes"][0]
        assert scene["narration"] == "Hello there."
        rev = scene["revisions"][-1]
        assert rev["type"] == "narration"
        assert rev["from"] == "Welcome."
        assert rev["phase"] == 0 and rev["iteration"] == 0
        assert doc["updated_at"] >= before

    def test_phase4_view_rerendered(self, project):  # SP2
        _, state_dir, client = project
        client.patch(
            "/api/project/storyboard/scenes/s2",
            json={"narration": "Fresh narration text."},
        )
        view = (state_dir / "phase4.md").read_text()
        assert "Fresh narration text." in view

    def test_unknown_scene(self, project):  # SP3
        _, _, client = project
        res = client.patch(
            "/api/project/storyboard/scenes/s99",
            json={"narration": "x"},
        )
        assert res.status_code == 404

    def test_no_storyboard(self, tmp_path, monkeypatch):  # SP4
        monkeypatch.setenv("INSTANTDEMO_PROJECT_DIR", str(tmp_path))
        from fastapi.testclient import TestClient
        from instantdemo.server.app import create_app

        res = TestClient(create_app()).patch(
            "/api/project/storyboard/scenes/s1", json={"narration": "x"}
        )
        assert res.status_code == 404
        assert "run the pipeline" in res.json()["detail"]

    def test_noop_appends_no_revision(self, project):  # SP5
        _, state_dir, client = project
        res = client.patch(
            "/api/project/storyboard/scenes/s1",
            json={"narration": "Welcome."},
        )
        assert res.status_code == 200
        doc = json.loads(storyboard.path_for(state_dir).read_text())
        assert doc["scenes"][0].get("revisions", []) == []

    def test_active_run_409(self, project):  # SP6
        _, _, client = project

        class FakeRun:
            status = "running"

        client.app.state.run_manager.active = FakeRun()
        try:
            res = client.patch(
                "/api/project/storyboard/scenes/s1",
                json={"narration": "x"},
            )
            assert res.status_code == 409
        finally:
            client.app.state.run_manager.active = None


class TestMarkerExposure:
    def test_default_false(self, project):  # SM1
        _, _, client = project
        assert client.get("/api/project").json()["storyboard_approved"] is False

    def test_true_round_trip(self, project):  # SM2
        _, state_dir, client = project
        s = state_mod.load(state_dir)
        s["storyboard_approved"] = True
        state_mod.save(state_dir, s)
        assert client.get("/api/project").json()["storyboard_approved"] is True
