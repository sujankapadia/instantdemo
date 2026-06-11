"""Per-project TTS configuration (M3, issue #59).

`<project>/tts.json` makes voice durable project state — provider,
stock voice or cloned reference, and pronunciation respellings — so
the pipeline render, the GUI's segment re-render, and the CLI all
speak with the same voice. The file is a sibling of intent.json and
the reference WAV lives INSIDE the project dir, so fixtures restore
with their voice.

Pronunciations are RESPELLINGS ("type it like it sounds"):
`{"match": "Evernote", "say": "Ever note"}`. They are applied to a
COPY of the narration immediately before synthesis — the speech text.
The display text (storyboard.json, demo-script.json, captions, the
GUI) is never mutated; the speech/display split is computed, not
stored. This is the provider-universal layer: it works for pocket-tts
(which has no phoneme stage to override) and equally for every other
provider. Phoneme-level overrides (Kokoro lexicon IPA) remain a
deferred, Kokoro-only concern — see issue #54 and
KOKORO_PRONUNCIATIONS.md.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

TTS_FILENAME = "tts.json"

DEFAULT_PROVIDER = "pocket-tts"
DEFAULT_VOICE = "alba"

# Snapshot of pocket-tts stock voices (the live list comes from a
# private API — `_ORIGINS_OF_PREDEFINED_VOICES` — so we vendor the
# names and prefer the live import when available).
POCKET_STOCK_VOICES: list[str] = [
    "alba", "anna", "azelma", "bill_boerst", "caro_davy", "charles",
    "cosette", "eponine", "estelle", "eve", "fantine", "george",
    "giovanni", "jane", "javert", "jean", "juergen", "lola",
    "marius", "mary", "michael", "paul", "peter_yearsley", "rafael",
    "stuart_bell", "vera",
]


def pocket_stock_voices() -> list[str]:
    """The stock voice catalog — live from pocket-tts when installed,
    falling back to the vendored snapshot."""
    try:
        from pocket_tts.utils.utils import (  # type: ignore[import-not-found]
            _ORIGINS_OF_PREDEFINED_VOICES,
        )

        return sorted(_ORIGINS_OF_PREDEFINED_VOICES.keys())
    except Exception:
        return list(POCKET_STOCK_VOICES)


@dataclass
class PronunciationEntry:
    """One respelling: wherever `match` appears as a whole word in
    narration, the synthesizer hears `say` instead."""

    match: str
    say: str


@dataclass
class TTSConfig:
    """The durable per-project voice. `ref_wav` (project-relative)
    overrides `voice` when set — the cloned "brand voice" path.
    `provider` is kept for CLI overrides and forward compat; the GUI
    only ever writes pocket-tts."""

    provider: str = DEFAULT_PROVIDER
    voice: str = DEFAULT_VOICE
    ref_wav: str | None = None
    pronunciations: list[PronunciationEntry] = field(default_factory=list)
    # {"given": true, "at": "<iso>"} — the cloning consent
    # affirmation, recorded with the artifact it covers. Cleared when
    # the reference is deleted.
    consent: dict[str, Any] | None = None


def tts_path(project_dir: Path) -> Path:
    return project_dir / TTS_FILENAME


def load(project_dir: Path) -> TTSConfig | None:
    """Read tts.json. Returns None when absent or malformed —
    callers fall back to `load_or_default`."""
    path = tts_path(project_dir)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(raw, dict):
        return None
    return TTSConfig(
        provider=raw.get("provider") or DEFAULT_PROVIDER,
        voice=raw.get("voice") or DEFAULT_VOICE,
        ref_wav=raw.get("ref_wav"),
        pronunciations=[
            PronunciationEntry(
                match=e.get("match", ""), say=e.get("say", "")
            )
            for e in (raw.get("pronunciations") or [])
            if isinstance(e, dict) and e.get("match") and e.get("say")
        ],
        consent=raw.get("consent"),
    )


def load_or_default(project_dir: Path) -> TTSConfig:
    return load(project_dir) or TTSConfig()


def save(project_dir: Path, config: TTSConfig) -> None:
    path = tts_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(config), indent=2) + "\n")


def resolve_ref_wav(project_dir: Path, config: TTSConfig) -> Path | None:
    """Absolute path to the cloning reference, or None when unset or
    missing on disk (a dangling ref_wav must not crash a render —
    the voice falls back to the configured stock voice)."""
    if not config.ref_wav:
        return None
    path = (project_dir / config.ref_wav).resolve()
    return path if path.exists() else None


def apply_pronunciations(
    text: str, entries: list[PronunciationEntry]
) -> str:
    """The speech-text transform: case-sensitive, whole-word literal
    substitution, entries applied in list order. Word boundaries
    keep "Evernote" from rewriting "Evernotes"."""
    if not text or not entries:
        return text
    for entry in entries:
        if not entry.match or not entry.say:
            continue
        text = re.sub(
            rf"\b{re.escape(entry.match)}\b", entry.say, text
        )
    return text


def speech_segments(
    segments: list[dict], entries: list[PronunciationEntry]
) -> list[dict]:
    """Copies of `segments` with narration transformed for synthesis.
    The originals are NEVER mutated — they are the display text that
    feeds the video overlay, demo-script.json, and (M6) captions."""
    if not entries:
        return segments
    out: list[dict] = []
    for seg in segments:
        copy = dict(seg)
        narration = copy.get("narration") or ""
        copy["narration"] = apply_pronunciations(narration, entries)
        out.append(copy)
    return out
