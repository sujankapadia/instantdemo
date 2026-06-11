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


class TestScopedPhases:
    def make_hypothesized(self) -> dict:
        doc = make_doc()
        for s in doc["scenes"]:
            s["selector"] = [".x"]
            s["wait_for"] = [".y"]
            s["pause_after_ms"] = 500
            s["status"] = "verified"
        return doc

    def test_scoped_gather_validator(self):  # G1
        from instantdemo.phases.gather import _make_validator

        doc = self.make_hypothesized()
        scope_ids = ["s3", "s4"]  # chapter B
        v = _make_validator(doc, scope_ids)
        enrich = {"selector": [".new"], "wait_for": [".w"],
                  "pause_after_ms": 800}
        assert v({"scenes": [
            {"id": "s3", **enrich}, {"id": "s4", **enrich},
        ]}) == []
        # Full-doc payload: out-of-scope ids are unknown
        problems = v({"scenes": [
            {"id": i, **enrich} for i in ("s1", "s3", "s4")
        ]})
        assert any("unknown scene ids" in p for p in problems)
        # Missing one chapter id
        problems = v({"scenes": [{"id": "s3", **enrich}]})
        assert any("missing scene ids: s4" in p for p in problems)

    def test_scoped_findings_guard(self):  # E1
        from instantdemo.phases.explore import (
            merge_findings_into_storyboard,
        )

        doc = self.make_hypothesized()
        out_of_scope_before = json.dumps(doc["scenes"][0], sort_keys=True)
        warnings = merge_findings_into_storyboard(
            doc,
            {"segments": [
                {"index": 3, "status": "PASS", "reason": "ok",
                 "selector_swapped": True, "from": ".x", "to": ".swapped"},
                {"index": 1, "status": "PASS", "reason": "sneaky",
                 "narration_revised": True, "narration_to": "CHANGED"},
            ]},
            iteration=1,
            scope_indices={3, 4},
        )
        assert doc["scenes"][2]["selector"] == [".swapped"]
        assert json.dumps(doc["scenes"][0], sort_keys=True) == out_of_scope_before
        assert any("outside the revised chapter" in w for w in warnings)


class TestSectionTiming:
    OLD = {
        "video": "demo.mp4",
        "total_duration_s": 30.0,
        "segments": [
            {"index": i, "start_s": i * 5.0, "end_s": (i + 1) * 5.0,
             "audio_duration_s": 4.0, "recorded_clean_duration_s": 5.0}
            for i in range(6)
        ],
    }

    def test_middle_chapter_rebuild(self):  # T1
        from instantdemo.render import rebuild_section_timing

        # Old chapter = segments 2..3 (2 rows); new chapter = 1 segment
        out = rebuild_section_timing(
            self.OLD, new_segments=[{}] * 5, start_idx=2, end_idx=2,
            old_chapter_len=2, section_slots_s=[3.0],
            section_recorded_s=[3.1], section_audio_s=[2.5],
            output_filename="demo.mp4",
        )
        rows = out["segments"]
        assert len(rows) == 5
        assert rows[:2] == self.OLD["segments"][:2]
        ch = rows[2]
        assert (ch["start_s"], ch["end_s"]) == (10.0, 13.0)
        assert ch["audio_duration_s"] == 2.5
        assert ch["recorded_clean_duration_s"] == 3.1
        # Tail: old rows 4,5 shifted by delta (-7.0), re-indexed 3,4
        assert [r["index"] for r in rows[3:]] == [3, 4]
        assert rows[3]["start_s"] == 13.0 and rows[3]["end_s"] == 18.0
        assert rows[4]["end_s"] == 23.0
        assert out["total_duration_s"] == 23.0

    def test_boundary_chapters(self):  # T2
        from instantdemo.render import rebuild_section_timing

        opening = rebuild_section_timing(
            self.OLD, [{}] * 5, start_idx=0, end_idx=0,
            old_chapter_len=2, section_slots_s=[4.0],
            section_recorded_s=[4.0], section_audio_s=[3.0],
            output_filename="demo.mp4",
        )
        assert opening["segments"][0]["start_s"] == 0.0
        assert opening["segments"][1]["start_s"] == 4.0  # old row 2 shifted
        closing = rebuild_section_timing(
            self.OLD, [{}] * 5, start_idx=4, end_idx=4,
            old_chapter_len=2, section_slots_s=[4.0],
            section_recorded_s=[4.0], section_audio_s=[3.0],
            output_filename="demo.mp4",
        )
        assert len(closing["segments"]) == 5
        assert closing["segments"][-1]["end_s"] == 24.0
        assert closing["total_duration_s"] == 24.0


class TestSectionRenderPlan:
    def make_context(self, tmp_path: Path, *, scenes, script_n, timing_n,
                     scope="B"):
        from instantdemo.phases import Context

        state_dir = tmp_path / ".instantdemo"
        state_dir.mkdir(exist_ok=True)
        doc = storyboard.new_document(title="t", url="u")
        for name in scenes:
            storyboard.add_scene(
                doc, title=name, narration="x", action="wait", section=name,
            )
        storyboard.save(state_dir, doc)
        (tmp_path / "demo-script.json").write_text(json.dumps({
            "segments": [{"action": "wait"}] * script_n
        }))
        (tmp_path / "demo.mp4").write_bytes(b"F")
        (state_dir / "segment-timing.json").write_text(json.dumps({
            "segments": [
                {"index": i, "start_s": float(i), "end_s": i + 1.0,
                 "recorded_clean_duration_s": 1.0}
                for i in range(timing_n)
            ],
        }))
        return Context(
            url="u", source=tmp_path, project=tmp_path, describe=None,
            state_dir=state_dir, output=tmp_path / "demo.mp4", tts=None,
            no_edit=True, section_scope=scope,
        )

    def test_aligned_plan(self, tmp_path: Path):  # P4
        from instantdemo.phases.render import _section_render_plan

        # A,B,B,C: chapter B = segments 1..2; old film had B of len 2
        ctx = self.make_context(
            tmp_path, scenes=["A", "B", "B", "C"], script_n=4, timing_n=4,
        )
        assert _section_render_plan(ctx) == (1, 2, 2)

    def test_misaligned_counts(self, tmp_path: Path):  # P5
        from instantdemo.phases.render import _section_render_plan

        # New film 4 segments (prefix 1, tail 1) but old timing has
        # only 2 rows → old_chapter_len = 0 → fallback.
        ctx = self.make_context(
            tmp_path, scenes=["A", "B", "B", "C"], script_n=4, timing_n=2,
        )
        assert _section_render_plan(ctx) is None

    def test_unavailable_cases(self, tmp_path: Path):  # P6
        from instantdemo.phases.render import _section_render_plan

        ctx = self.make_context(
            tmp_path, scenes=["A", "B", "B", "C"], script_n=4, timing_n=4,
            scope="Z",
        )
        assert _section_render_plan(ctx) is None
        ctx2 = self.make_context(
            tmp_path, scenes=["A", "B", "B", "C"], script_n=4, timing_n=4,
            scope=None,
        )
        assert _section_render_plan(ctx2) is None
        ctx3 = self.make_context(
            tmp_path, scenes=["A", "B", "B", "C"], script_n=4, timing_n=4,
        )
        (tmp_path / "demo.mp4").unlink()
        assert _section_render_plan(ctx3) is None


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