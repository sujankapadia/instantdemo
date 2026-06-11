"""Tests for the scoped chapter re-plan (M5b).
Spec: tests/test-specs/test_scoped_replan.md."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from instantdemo import storyboard
from instantdemo.phases.narrate import _scoped_validator, replace_chapter_scenes


def make_doc() -> dict:
    doc = storyboard.new_document(title="t", url="u")
    for name, n in (("A", 2), ("B", 2), ("C", 2)):
        for i in range(n):
            storyboard.add_scene(
                doc, title=f"{name}{i + 1}", narration="x", action="wait",
                section=name,
            )
    return doc  # ids s1..s6, next_scene_seq 7


NEW = [
    {"title": "New 1", "narration": "a", "action": "wait", "section": "B"},
    {"title": "New 2", "narration": "b", "action": "wait", "section": "B"},
    {"title": "New 3", "narration": "c", "action": "wait", "section": "B"},
]


class TestReplaceChapter:
    def test_middle_replacement(self, tmp_path: Path):  # S1
        doc = make_doc()
        a_objs = [json.dumps(s, sort_keys=True) for s in doc["scenes"][:2]]
        new_ids = replace_chapter_scenes(doc, "B", NEW)
        storyboard.save(tmp_path, doc)
        assert new_ids == ["s7", "s8", "s9"]
        titles = [s["title"] for s in doc["scenes"]]
        assert titles == ["A1", "A2", "New 1", "New 2", "New 3", "C1", "C2"]
        assert [s["index"] for s in doc["scenes"]] == list(range(1, 8))
        # A scenes untouched (modulo index, recomputed on save)
        for orig, now in zip(a_objs, doc["scenes"][:2]):
            assert orig == json.dumps(now, sort_keys=True)

    def test_old_ids_retired(self, tmp_path: Path):  # S2
        doc = make_doc()
        old_b_ids = {s["id"] for s in doc["scenes"] if s["section"] == "B"}
        replace_chapter_scenes(doc, "B", NEW)
        ids_now = {s["id"] for s in doc["scenes"]}
        assert old_b_ids.isdisjoint(ids_now)
        assert doc["next_scene_seq"] == 10

    def test_opening_chapter(self, tmp_path: Path):  # S3
        doc = make_doc()
        new = [dict(s, section="A") for s in NEW]
        replace_chapter_scenes(doc, "A", new)
        titles = [s["title"] for s in doc["scenes"]]
        assert titles == ["New 1", "New 2", "New 3", "B1", "B2", "C1", "C2"]

    def test_closing_chapter(self, tmp_path: Path):  # S4
        doc = make_doc()
        new = [dict(s, section="C") for s in NEW]
        replace_chapter_scenes(doc, "C", new)
        titles = [s["title"] for s in doc["scenes"]]
        assert titles == ["A1", "A2", "B1", "B2", "New 1", "New 2", "New 3"]

    def test_unknown_chapter(self):  # S5
        doc = make_doc()
        with pytest.raises(ValueError, match="no chapter"):
            replace_chapter_scenes(doc, "Z", NEW)

    def test_replaced_doc_validates(self, tmp_path: Path):  # S6
        doc = make_doc()
        replace_chapter_scenes(doc, "B", NEW)
        storyboard.save(tmp_path, doc)
        assert storyboard.validate_storyboard(doc, stage="planned") == []


class TestScopedValidator:
    def test_valid(self):  # SV1
        v = _scoped_validator("B")
        assert v({"scenes": NEW}) == []

    def test_wrong_section(self):  # SV2
        v = _scoped_validator("B")
        bad = [dict(NEW[0], section="C")]
        problems = v({"scenes": bad})
        assert any("revising ONLY that chapter" in p for p in problems)

    def test_shape_problems(self):  # SV3
        v = _scoped_validator("B")
        problems = v({"scenes": [
            {"title": "", "narration": "x", "action": "wait", "section": "B"},
            {"title": "ok", "narration": "x", "action": "fly", "section": "B"},
        ]})
        assert any("missing 'title'" in p for p in problems)
        assert any("unknown action" in p for p in problems)
        too_many = [dict(NEW[0], title=f"t{i}") for i in range(11)]
        assert any("too many" in p for p in v({"scenes": too_many}))


class TestPendingScopeLifecycle:
    @pytest.fixture()
    def client(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("INSTANTDEMO_PROJECT_DIR", str(tmp_path))
        (tmp_path / ".instantdemo").mkdir()
        from fastapi.testclient import TestClient
        from instantdemo.server.app import create_app

        with TestClient(create_app()) as c:
            # Don't actually execute phases — stub the background task.
            async def fake_execute(self, run, request, project):
                run.status = "complete"

            monkeypatch.setattr(
                type(c.app.state.run_manager), "_execute", fake_execute
            )
            yield tmp_path, c

    def _state(self, project: Path) -> dict:
        return json.loads(
            (project / ".instantdemo" / "state.json").read_text()
        )

    def test_scoped_leg_sets(self, client):  # P1
        project, c = client
        res = c.post("/api/runs", json={
            "phases": [2, 3, 4], "url": "http://x/",
            "section_scope": "Search",
            "section_instruction": "add the attachments filter",
        })
        assert res.status_code == 202, res.text
        assert self._state(project)["pending_scope"] == {
            "section": "Search",
            "instruction": "add the attachments filter",
        }

    def test_unscoped_planning_clears(self, client):  # P2
        project, c = client
        c.post("/api/runs", json={
            "phases": [2, 3, 4], "url": "http://x/",
            "section_scope": "Search", "section_instruction": "x",
        })
        c.app.state.run_manager.active = None  # let the next run start
        c.post("/api/runs", json={"phases": [2, 3, 4], "url": "http://x/"})
        assert "pending_scope" not in self._state(project)

    def test_approve_leg_receives_pending(self, client, monkeypatch):  # P3
        project, c = client
        captured: dict = {}

        async def capturing_execute(self, run, request, project_path):
            from instantdemo import state as state_mod
            pending = state_mod.load(
                project_path / ".instantdemo"
            ).get("pending_scope")
            captured["pending"] = pending
            run.status = "complete"

        monkeypatch.setattr(
            type(c.app.state.run_manager), "_execute", capturing_execute
        )
        c.post("/api/runs", json={
            "phases": [2, 3, 4], "url": "http://x/",
            "section_scope": "Search", "section_instruction": "y",
        })
        c.app.state.run_manager.active = None
        res = c.post("/api/runs", json={"phases": [5, 6], "url": "http://x/"})
        assert res.status_code == 202
        import time
        deadline = time.monotonic() + 5
        while "pending" not in captured and time.monotonic() < deadline:
            time.sleep(0.05)
        assert captured["pending"] == {
            "section": "Search", "instruction": "y",
        }