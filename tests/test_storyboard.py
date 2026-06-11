"""Unit tests for the storyboard contract (M0).

Spec: tests/test-specs/test_storyboard.md (IDs referenced in class
docstrings). Live-agent behavior is covered by the smoke scripts
(scripts/smoke.py, scripts/smoke_phase4_rehearsal.py).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from instantdemo import storyboard
from instantdemo.actions import validate_segments


def make_doc(**scene_overrides) -> dict:
    doc = storyboard.new_document(
        title="Test Demo",
        url="http://localhost:8001",
        summary="A short flow.",
        provenance={"tone": "casual"},
    )
    storyboard.add_scene(
        doc,
        title="Open the app",
        narration="Here's the app.",
        action="goto",
        target_hint="landing page",
        url="http://localhost:8001/",
        wait_for=[".note-item"],
    )
    storyboard.add_scene(
        doc,
        title="Click a note",
        narration="",
        action="click",
        target_hint="first note in the list",
        **scene_overrides,
    )
    return doc


class TestDocumentConstruction:
    """Spec rows D1-D4."""

    def test_ids_assigned_sequentially(self):  # D1
        doc = make_doc()
        assert [s["id"] for s in doc["scenes"]] == ["s1", "s2"]
        assert doc["next_scene_seq"] == 3

    def test_ids_never_reused_after_removal(self):  # D2
        doc = make_doc()
        doc["scenes"].pop(0)
        storyboard.add_scene(doc, title="New", narration="x", action="wait")
        ids = [s["id"] for s in doc["scenes"]]
        assert "s3" in ids and "s1" not in ids

    def test_save_recomputes_index_and_stamps(self, tmp_path: Path):  # D3
        doc = make_doc()
        doc["scenes"].reverse()
        storyboard.save(tmp_path, doc)
        loaded = storyboard.load(tmp_path)
        assert [s["index"] for s in loaded["scenes"]] == [1, 2]
        assert loaded["updated_at"]

    def test_load_missing_raises_migration_error(self, tmp_path: Path):  # D4
        with pytest.raises(RuntimeError, match="predates the storyboard"):
            storyboard.load(tmp_path)


class TestNormalizeCandidates:
    """Spec rows N1-N3."""

    def test_string_becomes_list(self):  # N1
        assert storyboard.normalize_candidates("a[href]") == ["a[href]"]

    def test_list_stripped_and_filtered(self):  # N2
        assert storyboard.normalize_candidates([" a ", "", "b"]) == ["a", "b"]

    def test_none_and_empty(self):  # N3
        assert storyboard.normalize_candidates(None) == []
        assert storyboard.normalize_candidates("") == []


class TestExtractJsonBlock:
    """Spec rows J1-J4."""

    def test_prose_then_block(self):  # J1
        text = 'Reasoning first.\n\n```json\n{"a": 1}\n```\n'
        assert storyboard.extract_json_block(text) == {"a": 1}

    def test_skips_invalid_block_finds_valid(self):  # J2
        text = '```json\n{broken\n```\nthen\n```json\n{"ok": true}\n```'
        assert storyboard.extract_json_block(text) == {"ok": True}

    def test_none_when_absent(self):  # J3
        assert storyboard.extract_json_block("no blocks here") is None

    def test_non_object_json_ignored(self):  # J4
        assert storyboard.extract_json_block("```json\n[1, 2]\n```") is None


class TestValidatePlanned:
    """Spec rows VP1-VP5."""

    def test_valid(self):  # VP1
        assert storyboard.validate_storyboard(make_doc(), stage="planned") == []

    def test_unknown_action(self):  # VP2
        doc = make_doc()
        doc["scenes"][0]["action"] = "wait_for_selector"
        problems = storyboard.validate_storyboard(doc, stage="planned")
        assert any("unknown action" in p and "allowed:" in p for p in problems)

    def test_duplicate_ids(self):  # VP3
        doc = make_doc()
        doc["scenes"][1]["id"] = doc["scenes"][0]["id"]
        problems = storyboard.validate_storyboard(doc, stage="planned")
        assert any("duplicate id" in p for p in problems)

    def test_no_scenes(self):  # VP4
        doc = storyboard.new_document(title="t", url="u")
        problems = storyboard.validate_storyboard(doc, stage="planned")
        assert problems == ["storyboard has no scenes"]

    def test_narration_must_be_string(self):  # VP5
        doc = make_doc()
        doc["scenes"][0]["narration"] = None
        problems = storyboard.validate_storyboard(doc, stage="planned")
        assert any("narration must be a string" in p for p in problems)


class TestValidateHypothesized:
    """Spec rows VH1-VH5."""

    def test_click_requires_selector(self):  # VH1
        doc = make_doc()  # click scene has no selector
        problems = storyboard.validate_storyboard(doc, stage="hypothesized")
        assert any(
            "requires non-empty 'selector' candidates" in p for p in problems
        )

    def test_valid_with_selector(self):  # VH2
        doc = make_doc(selector=["article.note-item", ".note-item"])
        assert storyboard.validate_storyboard(doc, stage="hypothesized") == []

    def test_scroll_needs_no_fields(self):  # VH3
        doc = storyboard.new_document(title="t", url="u")
        storyboard.add_scene(doc, title="s", narration="", action="scroll")
        assert storyboard.validate_storyboard(doc, stage="hypothesized") == []

    def test_pause_must_be_int(self):  # VH4
        doc = make_doc(selector=["x"], pause_after_ms="1500")
        problems = storyboard.validate_storyboard(doc, stage="hypothesized")
        assert any("pause_after_ms must be an integer" in p for p in problems)

    def test_evaluate_requires_expression(self):  # VH5
        doc = storyboard.new_document(title="t", url="u")
        storyboard.add_scene(doc, title="s", narration="", action="evaluate")
        problems = storyboard.validate_storyboard(doc, stage="hypothesized")
        assert any("requires the 'expression' field" in p for p in problems)


class TestValidateVerified:
    """Spec rows VV1-VV2."""

    def test_planned_scene_blocks(self):  # VV1
        doc = make_doc(selector=["x"])
        problems = storyboard.validate_storyboard(doc, stage="verified")
        assert any("must be verified or warn" in p for p in problems)

    def test_verified_and_warn_pass(self):  # VV2
        doc = make_doc(selector=["x"])
        for scene in doc["scenes"]:
            scene["status"] = "verified"
        doc["scenes"][1]["status"] = "warn"
        assert storyboard.validate_storyboard(doc, stage="verified") == []


class TestProjection:
    """Spec rows P1-P5."""

    def make_verified(self) -> dict:
        doc = storyboard.new_document(title="Proj Demo", url="u")
        storyboard.add_scene(
            doc, title="Open", narration="Welcome.", action="goto",
            url="http://x/", wait_for=[".item"], pause_after_ms=1500,
        )
        storyboard.add_scene(
            doc, title="Click", narration="", action="click",
            selector=["a.primary", 'a:has-text("Open")'],
        )
        storyboard.add_scene(
            doc, title="Scroll", narration="Scrolling.", action="evaluate",
            expression="window.scrollBy(0, 300)",
        )
        for scene in doc["scenes"]:
            scene["status"] = "verified"
        return doc

    def test_single_candidate_projects_as_string(self):  # P1
        script = storyboard.to_demo_script(self.make_verified())
        assert script["segments"][0]["wait_for"] == ".item"

    def test_multi_candidate_projects_as_array(self):  # P2
        script = storyboard.to_demo_script(self.make_verified())
        assert script["segments"][1]["selector"] == [
            "a.primary", 'a:has-text("Open")',
        ]

    def test_projection_passes_action_contract(self):  # P3
        script = storyboard.to_demo_script(self.make_verified())
        assert validate_segments(script["segments"]) == []

    def test_envelope(self):  # P4
        script = storyboard.to_demo_script(self.make_verified())
        assert script["title"] == "Proj Demo"
        assert script["resolution"] == {"width": 1280, "height": 720}
        assert script["segments"][0]["pause_after_ms"] == 1500

    def test_internal_fields_do_not_project(self):  # P5
        doc = self.make_verified()
        doc["scenes"][0]["notes"] = "fragile"
        script = storyboard.to_demo_script(doc)
        for seg in script["segments"]:
            assert "notes" not in seg
            assert "status" not in seg
            assert "id" not in seg


class TestMergeFindings:
    """Spec rows M1-M6 (explore.merge_findings_into_storyboard)."""

    def make_doc(self) -> dict:
        doc = make_doc(selector=["a.orig", "a.fallback"], wait_for=[".w"])
        for scene in doc["scenes"]:
            scene["status"] = "hypothesized"
        return doc

    def merge(self, doc, segments):
        from instantdemo.phases.explore import merge_findings_into_storyboard

        return merge_findings_into_storyboard(
            doc, {"segments": segments}, iteration=2
        )

    def test_selector_swap(self):  # M1
        doc = self.make_doc()
        warnings = self.merge(doc, [{
            "index": 2, "status": "PASS", "reason": "primary timed out",
            "selector_swapped": True, "from": "a.orig", "to": "a.new",
        }])
        scene = doc["scenes"][1]
        assert warnings == []
        assert scene["selector"] == ["a.new"]
        rev = scene["revisions"][-1]
        assert rev["type"] == "selector"
        assert rev["reason"] == "primary timed out"
        assert rev["iteration"] == 2

    def test_narration_reground(self):  # M2
        doc = self.make_doc()
        original = doc["scenes"][0]["narration"]
        self.merge(doc, [{
            "index": 1, "status": "PASS", "reason": "overclaim",
            "narration_revised": True, "narration_to": "Grounded text.",
        }])
        scene = doc["scenes"][0]
        assert scene["narration"] == "Grounded text."
        rev = scene["revisions"][-1]
        assert rev["type"] == "narration" and rev["from"] == original

    def test_updates_channel(self):  # M3
        doc = self.make_doc()
        self.merge(doc, [{
            "index": 1, "status": "PASS", "reason": "timing",
            "updates": {"wait_for": [".better"], "pause_after_ms": 2000},
        }])
        scene = doc["scenes"][0]
        assert scene["wait_for"] == [".better"]
        assert scene["pause_after_ms"] == 2000
        types = [r["type"] for r in scene["revisions"]]
        assert "wait_for" in types and "pause_after_ms" in types

    def test_status_mapping(self):  # M4
        doc = self.make_doc()
        self.merge(doc, [
            {"index": 1, "status": "WARN", "reason": "volatile data",
             "suggestion": None},
            {"index": 2, "status": "FAIL_SELECTOR", "reason": "not found",
             "suggestion": "check seed data"},
        ])
        assert doc["scenes"][0]["status"] == "warn"
        assert doc["scenes"][1]["status"] == "failed"
        v = doc["scenes"][1]["verification"]
        assert v["status"] == "FAIL_SELECTOR"
        assert v["suggestion"] == "check seed data"

    def test_out_of_range_index_warns(self):  # M5
        doc = self.make_doc()
        before = json.dumps(doc["scenes"])
        warnings = self.merge(doc, [
            {"index": 0, "status": "PASS", "reason": ""},
            {"index": 99, "status": "PASS", "reason": ""},
        ])
        assert len(warnings) == 2
        assert json.dumps(doc["scenes"]) == before

    def test_swap_without_to_warns(self):  # M6
        doc = self.make_doc()
        warnings = self.merge(doc, [{
            "index": 2, "status": "PASS", "reason": "",
            "selector_swapped": True, "from": "a.orig", "to": "",
        }])
        assert any("without 'to'" in w for w in warnings)
        assert doc["scenes"][1]["selector"] == ["a.orig", "a.fallback"]

    def test_action_kind_update(self):  # M7
        doc = self.make_doc()
        warnings = self.merge(doc, [{
            "index": 1, "status": "PASS",
            "reason": "click leaves the search active; Escape clears it",
            "updates": {"action": "press", "key": "Escape"},
        }])
        scene = doc["scenes"][0]
        assert warnings == []
        assert scene["action"] == "press"
        assert scene["key"] == "Escape"
        rev = scene["revisions"][-1]
        assert rev["type"] == "action"
        assert rev["to"] == "press Escape"

    def test_non_canonical_action_refused(self):  # M8
        doc = self.make_doc()
        original = doc["scenes"][0]["action"]
        warnings = self.merge(doc, [{
            "index": 1, "status": "PASS", "reason": "",
            "updates": {"action": "teleport"},
        }])
        assert any("not a canonical action" in w for w in warnings)
        assert doc["scenes"][0]["action"] == original

    def test_action_key_hygiene(self):  # M9
        doc = self.make_doc()
        doc["scenes"][0]["key"] = "Enter"  # stale from a prior shape
        self.merge(doc, [{
            "index": 1, "status": "PASS", "reason": "",
            "updates": {"action": "click"},
        }])
        assert "key" not in doc["scenes"][0]
        # press without an explicit key keeps whatever the scene has
        doc2 = self.make_doc()
        self.merge(doc2, [{
            "index": 1, "status": "PASS", "reason": "",
            "updates": {"action": "press"},
        }])
        assert doc2["scenes"][0]["action"] == "press"

    def test_option_wait_refused(self):  # M10
        doc = self.make_doc()
        original_wait = list(doc["scenes"][0].get("wait_for") or [])
        warnings = self.merge(doc, [{
            "index": 1, "status": "PASS", "reason": "",
            "updates": {"wait_for": ["#source-select option:nth-child(6)"]},
        }])
        assert any("<option>" in w for w in warnings)
        scene = doc["scenes"][0]
        assert list(scene.get("wait_for") or []) == original_wait
        assert all(r["type"] != "wait_for" for r in scene.get("revisions", []))


class TestViews:
    """Spec rows W1-W4."""

    def test_phase2_view_shape(self):  # W1
        doc = make_doc()
        view = storyboard.render_phase2_view(
            doc, {"tone": "casual", "audience": "general", "terminology": ""}
        )
        assert "<!-- ANSWER THESE BEFORE CONTINUING -->" in view
        assert "tone: casual" in view
        assert "### Segment 1 — Open the app" in view
        assert "- **Narration:** \"Here's the app.\"" in view
        assert "- **Narration:** (silent)" in view
        assert "- **Target:** landing page" in view

    def test_phase2_answer_block_parses(self):  # W2
        from instantdemo.checkpoints import parse_answer_block

        view = storyboard.render_phase2_view(
            make_doc(), {"tone": "warm", "audience": "x", "terminology": "y"}
        )
        answers = parse_answer_block(view)
        assert answers["tone"] == "warm"

    def test_phase3_view_shape(self):  # W3
        doc = make_doc(
            selector=["a.x", "a.y"], pause_after_ms=1000, notes="watch out"
        )
        view = storyboard.render_phase3_view(doc)
        assert "### Segment 2 — Click a note" in view
        assert "- **Selector:** `a.x`" in view
        assert "- **Selector fallbacks:** `a.y`" in view
        assert "- **pause_after_ms:** 1000" in view
        assert "- **Notes:** watch out" in view

    def test_phase4_view_shape(self):  # W4
        doc = make_doc(selector=["a.x"])
        scene = doc["scenes"][1]
        scene["status"] = "verified"
        scene["verification"] = {
            "status": "PASS", "reason": "resolved in 40ms", "suggestion": None,
        }
        scene["revisions"] = [{
            "type": "selector", "from": "a.old", "to": "a.x",
            "reason": "primary timed out", "iteration": 1, "phase": 4,
        }]
        findings = {"summary": {"overall": "OK"}, "segments": []}
        view = storyboard.render_phase4_view(doc, findings)
        assert "```json" in view
        assert '"overall": "OK"' in view
        assert "- **Verified:** PASS — resolved in 40ms" in view
        assert "- **Revised (selector):** `a.old` → `a.x`" in view
