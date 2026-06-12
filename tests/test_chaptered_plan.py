"""Tests for the chaptered cold start (M7).
Spec: tests/test-specs/test_chaptered_plan.md."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from instantdemo import storyboard
from instantdemo.phases import Context
from instantdemo.phases.narrate import _validate_outline


OUTLINE = {
    "title": "Tour",
    "summary": "A walkthrough.",
    "chapters": [
        {"name": "Opening", "purpose": "Set the scene.", "est_scenes": 2},
        {"name": "Search", "purpose": "Find things.", "est_scenes": 3},
        {"name": "Close", "purpose": "Land the point.", "est_scenes": 2},
    ],
}


def chapter_payload(name: str, n: int) -> dict:
    return {
        "scenes": [
            {
                "title": f"{name} scene {i + 1}",
                "narration": f"Narration for {name} {i + 1}.",
                "action": "wait",
                "section": name,
            }
            for i in range(n)
        ]
    }


class TestOutlineValidator:
    def test_valid(self):  # O1
        assert _validate_outline(dict(OUTLINE)) == []

    def test_chapter_count_bounds(self):  # O2
        one = dict(OUTLINE, chapters=OUTLINE["chapters"][:1])
        assert any("2 to 12" in p for p in _validate_outline(one))
        many = dict(
            OUTLINE,
            chapters=[
                {"name": f"C{i}", "purpose": "x", "est_scenes": 2}
                for i in range(13)
            ],
        )
        assert any("2 to 12" in p for p in _validate_outline(many))

    def test_shape_problems(self):  # O3
        bad = {
            "title": "T",
            "chapters": [
                {"name": "A", "purpose": "x", "est_scenes": 2},
                {"name": "A", "purpose": "", "est_scenes": 99},
            ],
        }
        problems = _validate_outline(bad)
        assert any("duplicate name" in p for p in problems)
        assert any("missing 'purpose'" in p for p in problems)
        assert any("est_scenes" in p for p in problems)


def make_context(tmp_path: Path, events: list | None = None) -> Context:
    state_dir = tmp_path / ".instantdemo"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "phase1.md").write_text(
        "<!-- ANSWER THESE BEFORE CONTINUING -->\nflow: tour\n"
        "<!-- /ANSWER -->\nApp model text."
    )
    return Context(
        url="http://x/",
        source=tmp_path,
        project=tmp_path,
        describe=None,
        state_dir=state_dir,
        output=tmp_path / "demo.mp4",
        tts=None,
        no_edit=True,
        client=object(),
        run_id="abcdef1234",
        event_emitter=(events.append if events is not None else None),
    )


class FakeResult:
    total_cost_usd = 0.05
    num_turns = 1
    duration_ms = 1000
    duration_api_ms = 900
    is_error = False
    stop_reason = "end_turn"
    session_id = "fake"
    usage: dict = {}


def install_canned(monkeypatch, *, continuity_rewrites=None, capture=None):
    """run_structured_query stub: outline call → OUTLINE; chapter
    calls → per-chapter payloads; continuity → rewrites."""

    async def fake(context, prompt, session_id, *, validate, phase_number):
        record = {
            "session_id": session_id,
            "prompt": prompt,
            "validate": validate,
        }
        if capture is not None:
            capture.append(record)
        if session_id.endswith("-outline"):
            payload = json.loads(json.dumps(OUTLINE))
        elif session_id.endswith("-cont"):
            payload = {
                "kind": "rewrite",
                "explanation": "smoothed",
                "rewrites": dict(continuity_rewrites or {}),
            }
        else:
            k = int(session_id.rsplit("-c", 1)[1])
            ch = OUTLINE["chapters"][k - 1]
            payload = chapter_payload(ch["name"], ch["est_scenes"])
        problems = validate(payload)
        assert problems == [], (session_id, problems)
        return payload, FakeResult()

    monkeypatch.setattr(
        "instantdemo.phases.narrate.run_structured_query", fake
    )


def run_phase2(tmp_path, monkeypatch, **kw):
    import asyncio

    from instantdemo.phases import narrate

    events: list = []
    capture: list = []
    install_canned(monkeypatch, capture=capture, **kw)
    recorded: dict = {}

    def fake_record(context, n, result, **kwargs):
        recorded.update(kwargs)

    monkeypatch.setattr(
        "instantdemo.phases.narrate.record_phase_result", fake_record
    )
    context = make_context(tmp_path, events)
    asyncio.run(narrate.run(context))
    return context, events, capture, recorded


class TestChapteredBuild:
    def test_build_order_and_validity(self, tmp_path, monkeypatch):  # CB1
        context, _, _, _ = run_phase2(tmp_path, monkeypatch)
        doc = storyboard.load(context.state_dir)
        sections = [s["section"] for s in doc["scenes"]]
        assert sections == ["Opening"] * 2 + ["Search"] * 3 + ["Close"] * 2
        assert [s["id"] for s in doc["scenes"]] == [
            f"s{i}" for i in range(1, 8)
        ]
        assert storyboard.validate_storyboard(doc, stage="planned") == []
        assert context.phase_artifact(2).exists()

    def test_chapter_validator_pins_section(self, tmp_path, monkeypatch):  # CB2
        _, _, capture, _ = run_phase2(tmp_path, monkeypatch)
        chapter_calls = [
            c for c in capture if "-c" in c["session_id"]
            and not c["session_id"].endswith(("-outline", "-cont"))
        ]
        wrong = chapter_payload("WrongChapter", 2)
        problems = chapter_calls[0]["validate"](wrong)
        assert any("revising ONLY that chapter" in p or "section" in p
                   for p in problems)

    def test_chapter_prompts_carry_context(self, tmp_path, monkeypatch):  # CB3
        _, _, capture, _ = run_phase2(tmp_path, monkeypatch)
        prompts_by_session = {
            c["session_id"]: c["prompt"] for c in capture
        }
        first = prompts_by_session["phase2-abcdef12-c1"]
        assert "OPENS the film" in first
        assert "1. Opening — Set the scene." in first  # the outline
        second = prompts_by_session["phase2-abcdef12-c2"]
        assert "Narration for Opening 2." in second  # boundary scene
        assert "3. Close — Land the point." in second

    def test_cost_aggregation(self, tmp_path, monkeypatch):  # CB4
        _, _, capture, recorded = run_phase2(tmp_path, monkeypatch)
        # outline + 3 chapters + continuity = 5 calls × $0.05
        assert recorded["cost_usd_total"] == pytest.approx(0.25)
        assert recorded["num_turns_total"] == 5

    def test_chapter_progress_events(self, tmp_path, monkeypatch):  # CB5
        _, events, _, _ = run_phase2(tmp_path, monkeypatch)
        progress = [e for e in events if e["type"] == "chapter_progress"]
        assert [(e["current"], e["total"], e["name"]) for e in progress] == [
            (1, 3, "Opening"), (2, 3, "Search"), (3, 3, "Close"),
        ]


class TestContinuityPass:
    def test_rewrites_applied(self, tmp_path, monkeypatch):  # CN1
        context, _, _, _ = run_phase2(
            tmp_path, monkeypatch,
            continuity_rewrites={"2": "Smoothed second narration."},
        )
        doc = storyboard.load(context.state_dir)
        assert doc["scenes"][1]["narration"] == "Smoothed second narration."
        assert doc["scenes"][0]["narration"] == "Narration for Opening 1."

    def test_empty_rewrites_accepted(self, tmp_path, monkeypatch):  # CN2
        context, _, _, _ = run_phase2(tmp_path, monkeypatch)
        doc = storyboard.load(context.state_dir)
        assert doc["scenes"][1]["narration"] == "Narration for Opening 2."

    def test_wrapper_keeps_style_rules(self):  # CN3
        from instantdemo.phases.narrate import _continuity_validator

        v = _continuity_validator(3)
        assert v({"kind": "rewrite", "explanation": "x", "rewrites": {}}) == []
        problems = v({
            "kind": "rewrite", "explanation": "x",
            "rewrites": {"9": "out of range", "1": "**markup**"},
        })
        assert any("out of range" in p for p in problems)
        assert any("markup" in p for p in problems)
