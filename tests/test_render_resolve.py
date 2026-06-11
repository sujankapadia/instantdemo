"""Unit tests for the renderer's TTS precedence resolution (M3).
Spec: tests/test-specs/test_render_resolve.md."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from instantdemo.render import BREATH_S, _resolve_tts, _slot_seconds
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


def test_breath_when_audio_fills_slot():  # B1
    assert _slot_seconds(3.0, 800) == 3.0 + BREATH_S


def test_pause_still_wins_when_longer():  # B2
    assert _slot_seconds(1.0, 5000) == 5.0


def test_missing_pause_is_safe():  # B3
    assert _slot_seconds(2.0, None) == 2.0 + BREATH_S


class _FakePage:
    """Records dispatch calls; wait_for_selector accepts anything."""

    def __init__(self):
        self.calls = []

    def wait_for_selector(self, selector, timeout=None, state=None):
        assert isinstance(selector, str)
        return object()

    def select_option(self, selector, value):
        self.calls.append(("select_option", selector, value))

    def press(self, selector, key):
        self.calls.append(("press", selector, key))

    def check(self, selector):
        self.calls.append(("check", selector))

    def uncheck(self, selector):
        self.calls.append(("uncheck", selector))


def test_candidate_arrays_resolve_to_one_string():  # D1
    from instantdemo.render import _ACTION_FIELD_MAP

    page = _FakePage()
    _ACTION_FIELD_MAP["select_option"](
        page, {"selector": ["#a", "#b"], "value": "v"}
    )
    _ACTION_FIELD_MAP["press"](page, {"selector": ["#a"], "key": "Escape"})
    _ACTION_FIELD_MAP["check"](page, {"selector": "#c"})
    _ACTION_FIELD_MAP["uncheck"](page, {"selector": ["#d", "#e"]})
    assert page.calls == [
        ("select_option", "#a", "v"),
        ("press", "#a", "Escape"),
        ("check", "#c"),
        ("uncheck", "#d"),
    ]
    for call in page.calls:
        assert isinstance(call[1], str)
