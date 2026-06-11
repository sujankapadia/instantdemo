"""Tests for the style/pace pass (M4).
Spec: tests/test-specs/test_revise.md."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from instantdemo import storyboard, takes
from instantdemo.revise import (
    apply_pace,
    apply_rewrites,
    validate_style_payload,
)


def vp(payload, n=3):
    return validate_style_payload(payload, segment_count=n)


class TestValidator:
    def test_valid_rewrite(self):  # V1
        assert vp({
            "kind": "rewrite",
            "explanation": "I'll soften scene two.",
            "rewrites": {"2": "Softer words."},
        }) == []

    def test_markup_rejected(self):  # V2
        problems = vp({
            "kind": "rewrite", "explanation": "x",
            "rewrites": {"1": "**bold** words", "2": "- a bullet",
                         "3": "has ``` fence"},
        })
        assert len([p for p in problems if "markup" in p]) == 3

    def test_bad_indices_and_text(self):  # V3
        problems = vp({
            "kind": "rewrite", "explanation": "x",
            "rewrites": {"9": "ok", "abc": "ok", "1": "  "},
        })
        assert any("out of range" in p for p in problems)
        assert any("not an integer" in p for p in problems)
        assert any("non-empty" in p for p in problems)

    def test_pace_bounds(self):  # V4
        assert vp({"kind": "pace", "explanation": "x", "pace_factor": 2.0})
        assert vp({"kind": "pace", "explanation": "x", "pace_factor": 1})
        assert vp({"kind": "pace", "explanation": "x"})
        assert vp({
            "kind": "pace", "explanation": "x", "pace_factor": 1.2
        }) == []

    def test_shape_mismatches(self):  # V5
        assert vp({"kind": "teleport", "explanation": "x"})
        assert vp({"kind": "voice", "explanation": "x"})
        assert vp({
            "kind": "pace", "explanation": "x", "pace_factor": 1.2,
            "rewrites": {"1": "no"},
        })


class TestApply:
    def test_rewrites_diff_semantics(self):  # A1
        segments = [
            {"narration": "one"}, {"narration": "two"}, {"narration": "three"},
        ]
        changed = apply_rewrites(segments, {"3": "THREE", "1": "one"})
        assert changed == [2]
        assert segments[2]["narration"] == "THREE"
        assert segments[0]["narration"] == "one"

    def test_pace_scaling(self):  # A2
        segments = [
            {"pause_after_ms": 1000}, {"pause_after_ms": 0}, {},
            {"pause_after_ms": 850},
        ]
        changed = apply_pace(segments, 1.2)
        assert changed == [0, 3]
        assert segments[0]["pause_after_ms"] == 1200
        assert segments[3]["pause_after_ms"] == 1020
        assert segments[1]["pause_after_ms"] == 0
        assert "pause_after_ms" not in segments[2]


def make_project(tmp_path: Path, *, scenes: int = 3) -> Path:
    (tmp_path / ".instantdemo").mkdir(exist_ok=True)
    (tmp_path / "demo.mp4").write_bytes(b"FILM")
    segments = [
        {"narration": f"Narration {i}.", "action": "wait",
         "pause_after_ms": 1000}
        for i in range(1, scenes + 1)
    ]
    (tmp_path / "demo-script.json").write_text(
        json.dumps({"segments": segments})
    )
    doc = storyboard.new_document(title="t", url="u")
    for i in range(1, scenes + 1):
        storyboard.add_scene(
            doc, title=f"S{i}", narration=f"Narration {i}.", action="wait"
        )
    storyboard.save(tmp_path / ".instantdemo", doc)
    return tmp_path


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("INSTANTDEMO_PROJECT_DIR", str(tmp_path))
    make_project(tmp_path)
    from fastapi.testclient import TestClient
    from instantdemo.server.app import create_app

    with TestClient(create_app()) as c:
        yield tmp_path, c


def canned(monkeypatch, payload):
    async def fake_query(context, prompt, session_id, *, validate,
                         phase_number):
        problems = validate(payload)
        assert problems == [], problems

        class R:
            total_cost_usd = 0.03

        return payload, R()

    monkeypatch.setattr(
        "instantdemo.server.routes.revise.run_structured_query", fake_query
    )


def stub_rerender(monkeypatch, calls):
    def fake(project, segments, idx, video, take_label="re-record"):
        calls.append({"idx": idx, "take_label": take_label})

        class R:
            pass

        return R()

    monkeypatch.setattr(
        "instantdemo.server.routes.segments._do_re_render_audio", fake
    )


def stub_client(monkeypatch, c):
    async def fake_ensure(self, cwd, roots):
        self._client = object()
        self._dispatcher = object()

    monkeypatch.setattr(
        type(c.app.state.run_manager), "_ensure_client", fake_ensure
    )


class TestReviseRoute:
    def test_rewrite_flow(self, client, monkeypatch):  # R1
        project, c = client
        canned(monkeypatch, {
            "kind": "rewrite",
            "explanation": "I'll soften the second scene.",
            "rewrites": {"2": "Softer narration two."},
        })
        calls: list = []
        stub_rerender(monkeypatch, calls)
        stub_client(monkeypatch, c)

        res = c.post("/api/project/revise",
                     json={"instruction": "make it warmer"})
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["kind"] == "rewrite"
        assert body["rewrites_applied"] == 1
        assert body["first_changed_index"] == 1
        assert body["take_n"] == 1
        # Take holds the PRE-mutation script
        take_script = json.loads(
            (takes.takes_dir(project) / "v1" / "demo-script.json").read_text()
        )
        assert take_script["segments"][1]["narration"] == "Narration 2."
        # Script mutated; storyboard synced with the instruction
        script = json.loads((project / "demo-script.json").read_text())
        assert script["segments"][1]["narration"] == "Softer narration two."
        doc = json.loads(
            (project / ".instantdemo" / "storyboard.json").read_text()
        )
        rev = doc["scenes"][1]["revisions"][-1]
        assert rev["reason"] == "make it warmer" and rev["phase"] == 0
        assert body["storyboard_synced"] is True
        # One re-render, with take_label=None (no double snapshot)
        assert calls == [{"idx": 1, "take_label": None}]

    def test_pace_slower(self, client, monkeypatch):  # R2
        project, c = client
        canned(monkeypatch, {
            "kind": "pace", "explanation": "I'll let it breathe.",
            "pace_factor": 1.2,
        })
        calls: list = []
        stub_rerender(monkeypatch, calls)
        stub_client(monkeypatch, c)
        body = c.post("/api/project/revise",
                      json={"instruction": "slower"}).json()
        assert body["needs_rerecord"] is False
        script = json.loads((project / "demo-script.json").read_text())
        assert script["segments"][0]["pause_after_ms"] == 1200
        assert len(calls) == 1

    def test_pace_faster(self, client, monkeypatch):  # R3
        project, c = client
        canned(monkeypatch, {
            "kind": "pace", "explanation": "I'll tighten it.",
            "pace_factor": 0.8,
        })
        calls: list = []
        stub_rerender(monkeypatch, calls)
        stub_client(monkeypatch, c)
        body = c.post("/api/project/revise",
                      json={"instruction": "faster"}).json()
        assert body["needs_rerecord"] is True
        script = json.loads((project / "demo-script.json").read_text())
        assert script["segments"][0]["pause_after_ms"] == 800
        assert calls == []

    def test_non_executable_kinds(self, client, monkeypatch):  # R4
        project, c = client
        canned(monkeypatch, {
            "kind": "voice", "explanation": "Try a deeper voice.",
            "suggestion": "marius",
        })
        stub_client(monkeypatch, c)
        body = c.post("/api/project/revise",
                      json={"instruction": "deeper voice"}).json()
        assert body["kind"] == "voice"
        assert body["suggestion"] == "marius"
        assert not takes.list_takes(project)
        script = json.loads((project / "demo-script.json").read_text())
        assert script["segments"][0]["narration"] == "Narration 1."

    def test_409_matrix(self, client, monkeypatch):  # R5
        _, c = client
        manager = c.app.state.run_manager

        class FakeRun:
            status = "running"

        manager.active = FakeRun()
        try:
            assert c.post("/api/project/revise",
                          json={"instruction": "x"}).status_code == 409
        finally:
            manager.active = None

        manager.revise_busy = True
        try:
            assert c.post("/api/project/revise",
                          json={"instruction": "x"}).status_code == 409
            run_res = c.post("/api/runs", json={
                "phases": [6], "url": "http://x/",
            })
            assert run_res.status_code == 409
        finally:
            manager.revise_busy = False

    def test_count_mismatch_skips_sync(self, client, monkeypatch):  # R6
        project, c = client
        # Storyboard with a different scene count
        doc = storyboard.new_document(title="t", url="u")
        storyboard.add_scene(doc, title="only", narration="x", action="wait")
        storyboard.save(project / ".instantdemo", doc)
        canned(monkeypatch, {
            "kind": "rewrite", "explanation": "x",
            "rewrites": {"2": "Changed two."},
        })
        calls: list = []
        stub_rerender(monkeypatch, calls)
        stub_client(monkeypatch, c)
        body = c.post("/api/project/revise",
                      json={"instruction": "y"}).json()
        assert body["storyboard_synced"] is False
        script = json.loads((project / "demo-script.json").read_text())
        assert script["segments"][1]["narration"] == "Changed two."

    def test_no_film_404(self, client):  # R7
        project, c = client
        (project / "demo.mp4").unlink()
        res = c.post("/api/project/revise", json={"instruction": "x"})
        assert res.status_code == 404
