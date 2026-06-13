"""Dispatch tests for the project-voice audio helper (M3).
Spec: tests/test-specs/test_segments_dispatch.md."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

from instantdemo.server.routes.segments import _generate_project_audio

SEGMENTS = [{"narration": "Evernote keeps notes", "action": "wait"}]


def write_tts(project: Path, **fields) -> None:
    (project / "tts.json").write_text(json.dumps(fields))


def test_legacy_default_pocket(tmp_path: Path, monkeypatch):  # D1
    calls = {}

    def fake_pocket(segments, tmp_dir, voice, ref, **kwargs):
        calls.update(voice=voice, ref=ref)
        return []

    monkeypatch.setattr(
        "instantdemo.render.generate_audio_pocket_tts", fake_pocket
    )
    _generate_project_audio(tmp_path, SEGMENTS, tmp_path)
    assert calls == {"voice": "alba", "ref": None}


def test_config_voice_and_ref(tmp_path: Path, monkeypatch):  # D2
    (tmp_path / ".instantdemo").mkdir()
    wav = tmp_path / ".instantdemo" / "voice-reference.wav"
    wav.write_bytes(b"RIFF")
    write_tts(
        tmp_path, provider="pocket-tts", voice="marius",
        ref_wav=".instantdemo/voice-reference.wav",
    )
    calls = {}

    def fake_pocket(segments, tmp_dir, voice, ref, **kwargs):
        calls.update(voice=voice, ref=ref)
        return []

    monkeypatch.setattr(
        "instantdemo.render.generate_audio_pocket_tts", fake_pocket
    )
    _generate_project_audio(tmp_path, SEGMENTS, tmp_path)
    assert calls["voice"] == "marius"
    assert calls["ref"] == wav.resolve()


def test_pronunciations_applied_speech_only(tmp_path: Path, monkeypatch):  # D3
    write_tts(
        tmp_path, provider="pocket-tts", voice="alba",
        pronunciations=[{"match": "Evernote", "say": "Ever note"}],
    )
    seen = {}

    def fake_pocket(segments, tmp_dir, voice, ref, **kwargs):
        seen["narration"] = segments[0]["narration"]
        return []

    monkeypatch.setattr(
        "instantdemo.render.generate_audio_pocket_tts", fake_pocket
    )
    originals = [dict(s) for s in SEGMENTS]
    _generate_project_audio(tmp_path, originals, tmp_path)
    assert seen["narration"] == "Ever note keeps notes"
    assert originals[0]["narration"] == "Evernote keeps notes"


def test_kokoro_config_dispatches(tmp_path: Path, monkeypatch):  # D4
    write_tts(tmp_path, provider="kokoro", voice="am_michael")
    calls = {}

    def fake_kokoro(segments, tmp_dir, voice, speed, **kwargs):
        calls.update(voice=voice, speed=speed)
        return []

    monkeypatch.setattr(
        "instantdemo.render.generate_audio_kokoro", fake_kokoro
    )
    _generate_project_audio(tmp_path, SEGMENTS, tmp_path)
    assert calls == {"voice": "am_michael", "speed": 1.0}


def test_system_exit_becomes_503(tmp_path: Path, monkeypatch):  # D5
    def exiting_pocket(segments, tmp_dir, voice, ref, **kwargs):
        print("  pocket-tts not installed", file=sys.stderr)
        raise SystemExit(1)

    monkeypatch.setattr(
        "instantdemo.render.generate_audio_pocket_tts", exiting_pocket
    )
    with pytest.raises(HTTPException) as exc_info:
        _generate_project_audio(tmp_path, SEGMENTS, tmp_path)
    assert exc_info.value.status_code == 503
    assert "pip install pocket-tts" in exc_info.value.detail
