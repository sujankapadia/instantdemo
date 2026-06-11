"""Unit tests for the explore-first Phase 1 (M1).

Spec: tests/test-specs/test_phase1_explore.md. Live behavior is
covered by scripts/smoke_phase1_explore.py.
"""

from __future__ import annotations

from pathlib import Path

from instantdemo.checkpoints import parse_answer_block
from instantdemo.intent import Intent
from instantdemo.phases import Context
from instantdemo.phases.analyze import (
    _normalized_proposal,
    _render_view,
    _validate_payload,
    new_screenshots,
)


def make_payload(**overrides) -> dict:
    payload = {
        "app_model": "## App\nA local notes viewer with 500 notes.",
        "proposed_intent": {
            "goal": "Show the notes list and open the Marketing note.",
            "audience": "non-technical users",
            "tone": None,
            "focus": [],
            "excludes": ["Import button (mutating)"],
            "addenda": [],
        },
        "screens": [
            {
                "name": "Notes list",
                "route": "/",
                "screenshot": "001-home.png",
                "notes": "500 notes, search box",
            }
        ],
        "warnings": ["Docs say port 8000; live app is on 8001."],
    }
    payload.update(overrides)
    return payload


def make_context(goal: str = "", tmp: Path = Path("/tmp/x")) -> Context:
    return Context(
        url="http://127.0.0.1:8001/",
        source=tmp,
        project=tmp,
        describe=None,
        state_dir=tmp / ".instantdemo",
        output=tmp / "demo.mp4",
        tts="kokoro",
        no_edit=True,
        intent=Intent(goal=goal),
    )


class TestValidatePayload:
    def test_valid(self):  # PV1
        assert _validate_payload(make_payload()) == []

    def test_empty_app_model(self):  # PV2
        problems = _validate_payload(make_payload(app_model="  "))
        assert any("app_model" in p for p in problems)

    def test_missing_goal(self):  # PV3
        payload = make_payload()
        payload["proposed_intent"]["goal"] = ""
        problems = _validate_payload(payload)
        assert any("goal" in p for p in problems)

    def test_focus_not_list(self):  # PV4
        payload = make_payload()
        payload["proposed_intent"]["focus"] = "everything"
        problems = _validate_payload(payload)
        assert any("focus" in p for p in problems)

    def test_bad_screens(self):  # PV5
        payload = make_payload(
            screens=[
                {"route": "/x"},
                {"name": "Evil", "screenshot": "../../etc/passwd.png"},
            ]
        )
        problems = _validate_payload(payload)
        assert len(problems) == 2

    def test_optional_sections_absent(self):  # PV6
        payload = make_payload()
        del payload["screens"]
        del payload["warnings"]
        assert _validate_payload(payload) == []

    def test_screenshot_exists_on_disk(self, tmp_path: Path):  # PV7
        (tmp_path / "001-home.png").write_bytes(b"x")
        assert _validate_payload(make_payload(), tmp_path) == []

    def test_no_screenshots_saved(self, tmp_path: Path):  # PV8
        problems = _validate_payload(make_payload(), tmp_path)
        assert any("no screenshots were saved" in p for p in problems)

    def test_missing_reference_named(self, tmp_path: Path):  # PV9
        (tmp_path / "001-home.png").write_bytes(b"x")
        payload = make_payload(
            screens=[
                {"name": "Home", "screenshot": "001-home.png"},
                {"name": "Ghost", "screenshot": "009-ghost.png"},
            ]
        )
        problems = _validate_payload(payload, tmp_path)
        assert any("009-ghost.png" in p for p in problems)


class TestNormalizedProposal:
    def test_fills_all_intent_keys(self):  # NP1
        payload = make_payload()
        payload["proposed_intent"] = {"goal": "Just this."}
        proposal = _normalized_proposal(payload)
        assert proposal == {
            "goal": "Just this.",
            "audience": None,
            "tone": None,
            "focus": [],
            "excludes": [],
            "addenda": [],
        }


class TestRenderView:
    def test_user_goal_wins(self):  # RV1
        view = _render_view(make_payload(), make_context(goal="My goal"))
        answers = parse_answer_block(view)
        assert answers["flow"] == "My goal"
        assert answers["url"] == "http://127.0.0.1:8001/"

    def test_proposal_goal_fallback(self):  # RV2
        view = _render_view(make_payload(), make_context())
        answers = parse_answer_block(view)
        assert answers["flow"].startswith("Show the notes list")

    def test_screens_and_warnings_render(self):  # RV3
        view = _render_view(make_payload(), make_context())
        assert "- **Notes list** (`/`)" in view
        assert "[screenshot: 001-home.png]" in view
        assert "## Warnings" in view
        assert "port 8000" in view


class TestNewScreenshots:
    def test_missing_dir(self, tmp_path: Path):  # NS1
        assert new_screenshots(tmp_path / "nope", set()) == []

    def test_diff_and_seen(self, tmp_path: Path):  # NS2
        (tmp_path / "002-b.png").write_bytes(b"x")
        (tmp_path / "001-a.png").write_bytes(b"x")
        seen = {"001-a.png"}
        fresh = new_screenshots(tmp_path, seen)
        assert fresh == ["002-b.png"]
        assert seen == {"001-a.png", "002-b.png"}
        assert new_screenshots(tmp_path, seen) == []

    def test_unsafe_names_ignored(self, tmp_path: Path):  # NS3
        (tmp_path / "notes.txt").write_bytes(b"x")
        (tmp_path / "ok.png").write_bytes(b"x")
        fresh = new_screenshots(tmp_path, set())
        assert fresh == ["ok.png"]
