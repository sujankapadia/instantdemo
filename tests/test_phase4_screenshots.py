"""Unit tests for Phase 4 rehearsal screenshots + the storyboard gate
marker (M2). Spec: tests/test-specs/test_phase4_screenshots.md."""

from __future__ import annotations

from pathlib import Path

from instantdemo import storyboard
from instantdemo.phases.explore import link_rehearsal_screenshots
from instantdemo.server.routes.runs import _storyboard_marker


def make_doc(n: int = 3) -> dict:
    doc = storyboard.new_document(title="t", url="u")
    for i in range(n):
        storyboard.add_scene(
            doc, title=f"Scene {i + 1}", narration="x", action="wait"
        )
    return doc


class TestLinkRehearsalScreenshots:
    def test_links_existing_only(self, tmp_path: Path):  # L1
        (tmp_path / "s1.png").write_bytes(b"x")
        (tmp_path / "s3.png").write_bytes(b"x")
        doc = make_doc(3)
        linked = link_rehearsal_screenshots(doc, tmp_path)
        assert linked == ["s1.png", "s3.png"]
        assert doc["scenes"][0]["rehearsal_screenshot"] == "s1.png"
        assert "rehearsal_screenshot" not in doc["scenes"][1]
        assert doc["scenes"][2]["rehearsal_screenshot"] == "s3.png"

    def test_pops_stale_reference(self, tmp_path: Path):  # L2
        doc = make_doc(1)
        doc["scenes"][0]["rehearsal_screenshot"] = "s1.png"  # prior run
        linked = link_rehearsal_screenshots(doc, tmp_path)
        assert linked == []
        assert "rehearsal_screenshot" not in doc["scenes"][0]

    def test_missing_dir(self, tmp_path: Path):  # L3
        doc = make_doc(2)
        assert link_rehearsal_screenshots(doc, tmp_path / "nope") == []
        assert all(
            "rehearsal_screenshot" not in s for s in doc["scenes"]
        )

    def test_binds_by_id_not_position(self, tmp_path: Path):  # L4
        doc = make_doc(3)
        # Simulate a scoped re-plan: scene s2 was replaced by s5 at
        # the same position (index 2).
        from instantdemo import storyboard as sb

        replacement = sb.add_scene(
            doc, title="New scene", narration="x", action="wait"
        )  # gets id s4... next call s5; we want a gap, so add twice
        replacement = sb.add_scene(
            doc, title="Newer scene", narration="x", action="wait"
        )
        doc["scenes"] = [doc["scenes"][0], replacement, doc["scenes"][2]]
        sb.save(tmp_path / ".sb", doc)  # recomputes indices: s1=1, s5=2, s3=3
        assert replacement["id"] == "s5" and replacement["index"] == 2

        (tmp_path / "s5.png").write_bytes(b"x")
        (tmp_path / "s2.png").write_bytes(b"x")  # stale file, old scene
        linked = link_rehearsal_screenshots(doc, tmp_path)
        assert linked == ["s5.png"]
        assert doc["scenes"][1]["rehearsal_screenshot"] == "s5.png"


class TestStoryboardMarker:
    def test_exploration_only_untouched(self):  # GM1
        assert _storyboard_marker([1]) is None

    def test_rehearsal_leg_resets(self):  # GM2
        assert _storyboard_marker([2, 3, 4]) is False

    def test_re_rehearse_resets(self):  # GM3
        assert _storyboard_marker([4]) is False

    def test_approve_run_sets(self):  # GM4
        assert _storyboard_marker([5, 6]) is True

    def test_regenerate_sets(self):  # GM5
        assert _storyboard_marker([1, 2, 3, 4, 5, 6]) is True

    def test_rerender_sets(self):  # GM6
        assert _storyboard_marker([6]) is True
