"""Unit tests for the per-project TTS config + speech-text transform
(M3). Spec: tests/test-specs/test_tts_config.md."""

from __future__ import annotations

import json
from pathlib import Path

from instantdemo import tts_config
from instantdemo.tts_config import (
    PronunciationEntry,
    TTSConfig,
    apply_pronunciations,
    speech_segments,
)


class TestLoadSave:
    def test_round_trip(self, tmp_path: Path):  # C1
        config = TTSConfig(
            voice="marius",
            ref_wav=".instantdemo/voice-reference.wav",
            pronunciations=[
                PronunciationEntry(match="Evernote", say="Ever note")
            ],
            consent={"given": True, "at": "2026-06-10T12:00:00Z"},
        )
        tts_config.save(tmp_path, config)
        loaded = tts_config.load(tmp_path)
        assert loaded == config

    def test_absent_file(self, tmp_path: Path):  # C2
        assert tts_config.load(tmp_path) is None
        default = tts_config.load_or_default(tmp_path)
        assert default.provider == "pocket-tts"
        assert default.voice == "alba"
        assert default.ref_wav is None
        assert default.pronunciations == []

    def test_malformed_json(self, tmp_path: Path):  # C3
        (tmp_path / "tts.json").write_text("{not json")
        assert tts_config.load(tmp_path) is None
        (tmp_path / "tts.json").write_text('["a", "list"]')
        assert tts_config.load(tmp_path) is None

    def test_incomplete_entries_dropped(self, tmp_path: Path):  # C4
        (tmp_path / "tts.json").write_text(json.dumps({
            "pronunciations": [
                {"match": "Evernote", "say": "Ever note"},
                {"match": "orphan"},
                {"say": "no match"},
                "not a dict",
            ]
        }))
        loaded = tts_config.load(tmp_path)
        assert loaded is not None
        assert loaded.pronunciations == [
            PronunciationEntry(match="Evernote", say="Ever note")
        ]


class TestResolveRefWav:
    def test_existing(self, tmp_path: Path):  # R1
        (tmp_path / ".instantdemo").mkdir()
        wav = tmp_path / ".instantdemo" / "voice-reference.wav"
        wav.write_bytes(b"RIFF")
        config = TTSConfig(ref_wav=".instantdemo/voice-reference.wav")
        assert tts_config.resolve_ref_wav(tmp_path, config) == wav.resolve()

    def test_dangling(self, tmp_path: Path):  # R2
        config = TTSConfig(ref_wav=".instantdemo/gone.wav")
        assert tts_config.resolve_ref_wav(tmp_path, config) is None

    def test_unset(self, tmp_path: Path):  # R3
        assert tts_config.resolve_ref_wav(tmp_path, TTSConfig()) is None


EVERNOTE = [PronunciationEntry(match="Evernote", say="Ever note")]


class TestApplyPronunciations:
    def test_whole_word(self):  # P1
        assert (
            apply_pronunciations("Evernote is great", EVERNOTE)
            == "Ever note is great"
        )

    def test_no_partial_word(self):  # P2
        assert (
            apply_pronunciations("My Evernotes archive", EVERNOTE)
            == "My Evernotes archive"
        )

    def test_case_sensitive(self):  # P3
        assert (
            apply_pronunciations("open evernote now", EVERNOTE)
            == "open evernote now"
        )

    def test_multi_entry_in_order(self):  # P4
        entries = [
            PronunciationEntry(match="ENEX", say="ee-nex"),
            PronunciationEntry(match="ee-nex file", say="ee-nex archive"),
        ]
        assert (
            apply_pronunciations("an ENEX file", entries)
            == "an ee-nex archive"
        )

    def test_multi_word_match(self):  # P5
        entries = [
            PronunciationEntry(match="Claude Code", say="clawed code")
        ]
        assert (
            apply_pronunciations("using Claude Code daily", entries)
            == "using clawed code daily"
        )

    def test_empty_inputs(self):  # P6
        assert apply_pronunciations("", EVERNOTE) == ""
        assert apply_pronunciations("text", []) == "text"


class TestSpeechSegments:
    def test_originals_unmutated(self):  # S1 — the display-text guarantee
        originals = [
            {"narration": "Evernote keeps notes", "action": "goto"},
            {"narration": "", "action": "wait"},
        ]
        speech = speech_segments(originals, EVERNOTE)
        assert speech[0]["narration"] == "Ever note keeps notes"
        assert speech[1]["narration"] == ""
        assert originals[0]["narration"] == "Evernote keeps notes"
        assert speech[0] is not originals[0]

    def test_no_entries_fast_path(self):  # S2
        originals = [{"narration": "hello"}]
        assert speech_segments(originals, []) is originals
