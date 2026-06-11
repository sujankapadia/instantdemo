"""Unit tests for the renderer's TTS precedence resolution (M3).
Spec: tests/test-specs/test_render_resolve.md."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from instantdemo.render import _resolve_tts
from instantdemo.tts_config import PronunciationEntry, TTSConfig


def make_args(**overrides) -> Namespace:
    base = dict(
        tts=None, kokoro_voice=None, kokoro_speed=None,
        pocket_voice=None, pocket_ref=None,
    )
    base.update(overrides)
    return Namespace(**base)


def test_no_flags_no_config():  # T1
    r = _resolve_tts(make_args(), None, None)
    assert (r.provider, r.voice, r.ref) == ("pocket-tts", "alba", None)


def test_config_wins_without_flags(tmp_path: Path):  # T2
    (tmp_path / ".instantdemo").mkdir()
    wav = tmp_path / ".instantdemo" / "voice-reference.wav"
    wav.write_bytes(b"RIFF")
    config = TTSConfig(
        voice="marius", ref_wav=".instantdemo/voice-reference.wav"
    )
    r = _resolve_tts(make_args(), config, tmp_path)
    assert r.provider == "pocket-tts"
    assert r.voice == "marius"
    assert r.ref == wav.resolve()


def test_provider_flag_resets_foreign_voice():  # T3
    config = TTSConfig(provider="pocket-tts", voice="marius")
    r = _resolve_tts(make_args(tts="kokoro"), config, None)
    assert r.provider == "kokoro"
    assert r.voice == "af_heart"


def test_voice_flag_wins():  # T4
    config = TTSConfig(voice="marius")
    r = _resolve_tts(make_args(pocket_voice="javert"), config, None)
    assert r.voice == "javert"


def test_ref_flag_wins(tmp_path: Path):  # T5
    (tmp_path / ".instantdemo").mkdir()
    config_ref = tmp_path / ".instantdemo" / "voice-reference.wav"
    config_ref.write_bytes(b"RIFF")
    flag_ref = tmp_path / "other.wav"
    config = TTSConfig(ref_wav=".instantdemo/voice-reference.wav")
    r = _resolve_tts(make_args(pocket_ref=flag_ref), config, tmp_path)
    assert r.ref == flag_ref


def test_dangling_config_ref(tmp_path: Path):  # T6
    config = TTSConfig(ref_wav=".instantdemo/gone.wav")
    r = _resolve_tts(make_args(), config, tmp_path)
    assert r.ref is None
    assert r.voice == "alba"


def test_pronunciations_survive_provider_override():  # T7
    config = TTSConfig(
        pronunciations=[PronunciationEntry(match="ENEX", say="ee-nex")]
    )
    r = _resolve_tts(make_args(tts="kokoro"), config, None)
    assert r.pronunciations == config.pronunciations
