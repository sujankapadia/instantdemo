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
    def __init__(self):
        self.total_cost_usd = 0.05

    num_turns = 1
    duration_ms = 1000
    duration_api_ms = 900
    is_error = False
    stop_reason = "end_turn"
    session_id = "fake"
    usage: dict = {}


def install_canned(monkeypatch, *, continuity_rewrites=None, capture=None):
    """run_structured_query stub for the SINGLE-session phase 2:
    routes by prompt content (call 1 = outline; 'Now plan chapter k'
    = that chapter; the script-editor ask = continuity) and emulates
    a session's CUMULATIVE total_cost_usd."""
    calls = {"n": 0, "chapter": 0}

    async def fake(context, prompt, session_id, *, validate, phase_number):
        calls["n"] += 1
        record = {
            "session_id": session_id,
            "prompt": prompt,
            "validate": validate,
        }
        if capture is not None:
            capture.append(record)
        if calls["n"] == 1:
            payload = json.loads(json.dumps(OUTLINE))
        elif "script editor" in prompt:
            payload = {
                "kind": "rewrite",
                "explanation": "smoothed",
                "rewrites": dict(continuity_rewrites or {}),
            }
        else:
            calls["chapter"] += 1
            ch = OUTLINE["chapters"][calls["chapter"] - 1]
            payload = chapter_payload(ch["name"], ch["est_scenes"])
        problems = validate(payload)
        assert problems == [], (session_id, problems)
        result = FakeResult()
        result.total_cost_usd = 0.05 * calls["n"]  # cumulative
        return payload, result

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
            c for c in capture if "Now plan chapter" in c["prompt"]
        ]
        wrong = chapter_payload("WrongChapter", 2)
        problems = chapter_calls[0]["validate"](wrong)
        assert any("revising ONLY that chapter" in p or "section" in p
                   for p in problems)

    def test_chapter_prompts_carry_context(self, tmp_path, monkeypatch):  # CB3
        _, _, capture, _ = run_phase2(tmp_path, monkeypatch)
        # One session throughout.
        assert {c["session_id"] for c in capture} == {"phase2-abcdef12"}
        chapter_prompts = [
            c["prompt"] for c in capture
            if "Now plan chapter" in c["prompt"]
        ]
        first, second = chapter_prompts[0], chapter_prompts[1]
        assert "OPENS the film" in first
        assert "1. Opening — Set the scene." in first  # full context
        assert "Codebase analysis" in first
        # Continuations are short: boundary narration, no re-sent
        # outline or analysis.
        assert "Narration for Opening 2." in second
        assert "Codebase analysis" not in second
        assert "1. Opening — Set the scene." not in second

    def test_cost_accounting(self, tmp_path, monkeypatch):  # CB4
        _, _, capture, recorded = run_phase2(tmp_path, monkeypatch)
        # One session, 5 calls; the fake's cumulative total ends at
        # 5 × $0.05 — the recorded phase cost is that final total.
        assert len(capture) == 5
        assert recorded["cost_usd_total"] == pytest.approx(0.25)
        assert recorded["num_turns_total"] == 5

    def test_chapter_progress_events(self, tmp_path, monkeypatch):  # CB5
        _, events, _, _ = run_phase2(tmp_path, monkeypatch)
        progress = [e for e in events if e["type"] == "chapter_progress"]
        assert [(e["current"], e["total"], e["name"]) for e in progress] == [
            (1, 3, "Opening"), (2, 3, "Search"), (3, 3, "Close"),
        ]


def make_planned_doc(tmp_path: Path) -> Context:
    """A 3-chapter planned board on disk, ready for phase 3/4."""
    context = make_context(tmp_path)
    doc = storyboard.new_document(title="Tour", url="http://x/")
    for ch in OUTLINE["chapters"]:
        for i in range(2):
            storyboard.add_scene(
                doc, title=f"{ch['name']} {i + 1}", narration="x",
                action="wait", section=ch["name"],
            )
    storyboard.save(context.state_dir, doc)
    return context


class TestGatherLoop:
    def test_loop_per_chapter(self, tmp_path, monkeypatch):  # GL1 + GL2
        import asyncio

        from instantdemo.phases import gather

        calls: list[dict] = []

        counter = {"n": 0}

        async def fake(context, prompt, session_id, *, validate,
                       phase_number):
            doc = storyboard.load(context.state_dir)
            counter["n"] += 1
            k = counter["n"]
            name = OUTLINE["chapters"][k - 1]["name"]
            ids = [s["id"] for s in doc["scenes"] if s["section"] == name]
            payload = {"scenes": [
                {"id": i, "selector": [".x"], "wait_for": [".y"],
                 "pause_after_ms": 500}
                for i in ids
            ]}
            # GL2: this chapter's validation must pass while later
            # chapters are still bare.
            problems = validate(payload)
            assert problems == [], (session_id, problems)
            calls.append({"session_id": session_id, "ids": ids,
                          "prompt": prompt, "validate": validate})
            return payload, FakeResult()

        monkeypatch.setattr(
            "instantdemo.phases.gather.run_structured_query", fake
        )
        recorded: dict = {}
        monkeypatch.setattr(
            "instantdemo.phases.gather.record_phase_result",
            lambda c, n, r, **kw: recorded.update(kw),
        )
        context = make_planned_doc(tmp_path)
        asyncio.run(gather.run(context))

        assert {c["session_id"] for c in calls} == {"phase3-abcdef12"}
        assert "app being demoed" in calls[0]["prompt"]
        assert "Next chapter" in calls[1]["prompt"]
        assert "app being demoed" not in calls[1]["prompt"]
        # Validator pins each chapter's ids: a foreign id is rejected.
        foreign = {"scenes": [
            {"id": "s1", "selector": [".x"], "wait_for": [".y"],
             "pause_after_ms": 1}
        ]}
        assert calls[1]["validate"](foreign)  # s1 belongs to chapter 1
        doc = storyboard.load(context.state_dir)
        assert storyboard.validate_storyboard(doc, stage="hypothesized") == []
        # Single session: the phase cost is the last call's total.
        assert recorded["cost_usd_total"] == pytest.approx(0.05)


def explore_findings(doc: dict, section: str, status: str = "PASS") -> str:
    segs = [
        {"index": s["index"], "status": status, "reason": "ok"}
        for s in doc["scenes"] if s["section"] == section
    ]
    return "report\n```json\n" + json.dumps({"segments": segs}) + "\n```\n"


class TestExploreLoop:
    def _run(self, tmp_path, monkeypatch, blocked_chapter=None,
             dispatcher=None):
        import asyncio

        from instantdemo.phases import explore

        sessions: list[str] = []

        async def fake_query(context, prompt, *, session_id):
            sessions.append(session_id)
            if dispatcher is not None:
                # Emulate the live delta accounting: the SDK reports
                # every result under ITS OWN session UUID (one key for
                # the whole client), never our logical phase4-…-cN ids.
                totals = dispatcher.session_cost_totals
                totals["0d673829-sdk-uuid"] = (
                    totals.get("0d673829-sdk-uuid", 0.0) + 0.10
                )
            doc = storyboard.load(context.state_dir)
            k = int(session_id.rsplit("-c", 1)[1])
            name = OUTLINE["chapters"][k - 1]["name"]
            status = (
                "FAIL_SELECTOR" if name == blocked_chapter else "PASS"
            )
            return explore_findings(doc, name, status), FakeResult()

        monkeypatch.setattr(
            "instantdemo.phases.explore.run_query_on_client", fake_query
        )

        async def fake_ensure(*args, **kwargs):
            return None

        monkeypatch.setattr(
            "instantdemo.phases.explore._ensure_screenshots", fake_ensure
        )
        monkeypatch.setattr(
            "instantdemo.phases.explore.record_phase_result",
            lambda c, n, r, **kw: None,
        )
        context = make_planned_doc(tmp_path)
        context.dispatcher = dispatcher
        # Phase 4 needs hypothesized scenes; bulk-enrich them.
        doc = storyboard.load(context.state_dir)
        for s in doc["scenes"]:
            s["selector"] = [".x"]
            s["wait_for"] = [".y"]
            s["pause_after_ms"] = 500
            s["status"] = "hypothesized"
        storyboard.save(context.state_dir, doc)

        err = None
        try:
            asyncio.run(explore.run(context))
        except RuntimeError as exc:
            err = exc
        return context, sessions, err

    def test_all_pass(self, tmp_path, monkeypatch):  # EL1
        import json as _json

        context, sessions, err = self._run(tmp_path, monkeypatch)
        assert err is None
        assert sessions == [
            "phase4-abcdef12-c1", "phase4-abcdef12-c2", "phase4-abcdef12-c3",
        ]
        doc = storyboard.load(context.state_dir)
        assert all(s["status"] == "verified" for s in doc["scenes"])
        st = _json.loads(
            (context.state_dir / "state.json").read_text()
        )
        combined = st["phases"]["4"]["explore_findings"]["segments"]
        assert sorted(s["index"] for s in combined) == list(range(1, 7))
        assert st["phases"]["4"]["explore_overall"] == "OK"

    def test_state_cost_is_key_agnostic(self, tmp_path, monkeypatch):  # EL4
        import json as _json
        from types import SimpleNamespace

        dispatcher = SimpleNamespace(session_cost_totals={})
        context, sessions, err = self._run(
            tmp_path, monkeypatch, dispatcher=dispatcher
        )
        assert err is None
        assert len(sessions) == 3
        st = _json.loads(
            (context.state_dir / "state.json").read_text()
        )
        # Three chapter calls at $0.10 each, all accumulated under the
        # SDK's UUID key — the phase total must still come out right.
        assert st["phases"]["4"]["cost_usd"] == pytest.approx(0.30)

    def test_blocked_fails_fast(self, tmp_path, monkeypatch):  # EL2
        context, sessions, err = self._run(
            tmp_path, monkeypatch, blocked_chapter="Search"
        )
        assert err is not None and "block the render" in str(err)
        # Chapter 2 retried once in its own session (convergence),
        # then stopped on the unchanged failure signature; chapter 3
        # never rehearsed.
        assert sessions == [
            "phase4-abcdef12-c1",
            "phase4-abcdef12-c2",
            "phase4-abcdef12-c2",
        ]
        doc = storyboard.load(context.state_dir)
        search = [s for s in doc["scenes"] if s["section"] == "Search"]
        assert all(s["status"] == "failed" for s in search)


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
