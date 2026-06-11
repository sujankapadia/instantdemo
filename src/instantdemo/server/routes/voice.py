"""Voice & pronunciation API (M3, #59): the GUI surface over
tts.json. Stock-voice selection, cloned-reference upload with
validation + consent, pronunciation respellings, and instant audio
preview — the listen-check that stands in for phoneme-level
verification (pocket-tts has no G2P layer to interrogate; the only
way to know how it says a word is to hear it).

Heavy synthesis runs in executor threads with a module-level model
cache (threading.Lock — executor context, not asyncio). pocket-tts /
torch are imported lazily inside workers only; route availability
checks use find_spec so the dialog opens instantly.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import (
    APIRouter,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from pydantic import BaseModel

from instantdemo import tts_config as tts_config_mod
from instantdemo.tts_config import PronunciationEntry, TTSConfig

router = APIRouter(prefix="/api", tags=["voice"])

REFERENCE_RELPATH = ".instantdemo/voice-reference.wav"
_MIN_REF_SECONDS = 4.0
_MAX_REF_SECONDS = 120.0
_SILENCE_PEAK_DBFS = -50.0
_DEFAULT_PREVIEW_TEXT = (
    "Here's a quick preview of this voice narrating your demo."
)

# Loaded TTS models + pocket voice-states, kept for the server's
# lifetime so previews after the first are sub-second. Guarded by a
# plain threading.Lock — synthesis runs in executor threads.
_PREVIEW_CACHE: dict[str, Any] = {}
_PREVIEW_LOCK = threading.Lock()


class PronunciationBody(BaseModel):
    match: str
    say: str


class VoiceConfigBody(BaseModel):
    provider: str
    voice: str
    ref_wav: str | None = None
    pronunciations: list[PronunciationBody] = []
    consent: dict[str, Any] | None = None


class VoiceState(BaseModel):
    config: VoiceConfigBody
    persisted: bool
    ref_exists: bool
    pocket_installed: bool
    voices: list[str]


class VoiceUpdate(BaseModel):
    voice: str | None = None
    pronunciations: list[PronunciationBody] | None = None


class PreviewRequest(BaseModel):
    text: str | None = None
    voice: str | None = None
    use_reference: bool | None = None
    pronunciations: list[PronunciationBody] | None = None


def _project_dir() -> Path:
    override = os.environ.get("INSTANTDEMO_PROJECT_DIR")
    return Path(override).resolve() if override else Path.cwd()


def _reject_during_runs(request: Request) -> None:
    manager = getattr(request.app.state, "run_manager", None)
    active = getattr(manager, "active", None)
    if active is not None and active.status in (
        "running", "starting", "paused"
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="a run is in progress; wait for it to finish",
        )


def _config_body(config: TTSConfig) -> VoiceConfigBody:
    return VoiceConfigBody(
        provider=config.provider,
        voice=config.voice,
        ref_wav=config.ref_wav,
        pronunciations=[
            PronunciationBody(match=e.match, say=e.say)
            for e in config.pronunciations
        ],
        consent=config.consent,
    )


def _entries(bodies: list[PronunciationBody]) -> list[PronunciationEntry]:
    return [
        PronunciationEntry(match=b.match.strip(), say=b.say.strip())
        for b in bodies
        if b.match.strip() and b.say.strip()
    ]


@router.get("/project/voice", response_model=VoiceState)
def get_voice() -> VoiceState:
    project = _project_dir()
    config = tts_config_mod.load(project)
    effective = config or TTSConfig()
    return VoiceState(
        config=_config_body(effective),
        persisted=config is not None,
        ref_exists=tts_config_mod.resolve_ref_wav(project, effective)
        is not None,
        pocket_installed=importlib.util.find_spec("pocket_tts") is not None,
        voices=tts_config_mod.pocket_stock_voices(),
    )


@router.put("/project/voice", response_model=VoiceState)
def update_voice(update: VoiceUpdate, request: Request) -> VoiceState:
    """Partial update of voice / pronunciations. The GUI only writes
    pocket-tts configs; provider stays whatever the config already
    says (CLI users may have set kokoro deliberately)."""
    _reject_during_runs(request)
    project = _project_dir()
    config = tts_config_mod.load_or_default(project)
    if update.voice is not None:
        if update.voice not in tts_config_mod.pocket_stock_voices():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"unknown voice {update.voice!r}",
            )
        config.voice = update.voice
    if update.pronunciations is not None:
        config.pronunciations = _entries(update.pronunciations)
    tts_config_mod.save(project, config)
    return get_voice()


def _probe_duration_s(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise ValueError("couldn't read that file as audio")
    try:
        return float(json.loads(out.stdout)["format"]["duration"])
    except (KeyError, ValueError, json.JSONDecodeError):
        raise ValueError("couldn't read that file as audio")


def _peak_dbfs(path: Path) -> float:
    """Peak level via ffmpeg's volumedetect (no numpy dependency)."""
    out = subprocess.run(
        ["ffmpeg", "-i", str(path), "-af", "volumedetect",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    for line in out.stderr.splitlines():
        if "max_volume:" in line:
            try:
                return float(line.split("max_volume:")[1].split("dB")[0])
            except (IndexError, ValueError):
                break
    raise ValueError("couldn't measure the recording's level")


def _validate_and_store_reference(upload_path: Path, dest: Path) -> None:
    """Bake-off finding 8 written into code: reject the bad take at
    upload time, in plain language."""
    duration = _probe_duration_s(upload_path)
    if duration < _MIN_REF_SECONDS:
        raise ValueError(
            f"too short: {duration:.1f}s — record at least "
            f"{_MIN_REF_SECONDS:.0f}s (10-30s works best)"
        )
    if duration > _MAX_REF_SECONDS:
        raise ValueError(
            f"too long: {duration:.0f}s — trim to 10-30s of clean speech"
        )
    peak = _peak_dbfs(upload_path)
    if peak < _SILENCE_PEAK_DBFS:
        raise ValueError(
            "the recording is silent — check that the right "
            "microphone was selected, then re-record"
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    converted = subprocess.run(
        ["ffmpeg", "-y", "-i", str(upload_path),
         "-ac", "1", "-ar", "24000", str(dest)],
        capture_output=True, text=True,
    )
    if converted.returncode != 0:
        raise ValueError("couldn't convert the recording to WAV")


@router.post("/project/voice/reference", response_model=VoiceState)
async def upload_reference(
    request: Request,
    file: UploadFile = File(...),
    consent: bool = Form(False),
) -> VoiceState:
    _reject_during_runs(request)
    if not consent:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="confirm you have the right to use this voice",
        )
    project = _project_dir()
    suffix = Path(file.filename or "upload").suffix or ".bin"
    with tempfile.NamedTemporaryFile(
        suffix=suffix, delete=False
    ) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)
    try:
        dest = project / REFERENCE_RELPATH
        try:
            await asyncio.to_thread(
                _validate_and_store_reference, tmp_path, dest
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
        config = tts_config_mod.load_or_default(project)
        config.ref_wav = REFERENCE_RELPATH
        config.consent = {
            "given": True,
            "at": datetime.now(timezone.utc).isoformat(),
        }
        tts_config_mod.save(project, config)
        # A new reference invalidates any cached voice-state for the
        # old file.
        with _PREVIEW_LOCK:
            _PREVIEW_CACHE.pop(f"pocket-state:ref:{dest}", None)
        return get_voice()
    finally:
        tmp_path.unlink(missing_ok=True)


@router.delete("/project/voice/reference", response_model=VoiceState)
def delete_reference(request: Request) -> VoiceState:
    _reject_during_runs(request)
    project = _project_dir()
    ref = project / REFERENCE_RELPATH
    ref.unlink(missing_ok=True)
    config = tts_config_mod.load_or_default(project)
    config.ref_wav = None
    config.consent = None
    tts_config_mod.save(project, config)
    return get_voice()


def _synthesize_preview(
    text: str, voice: str, ref: Path | None
) -> bytes:
    """Blocking pocket-tts synthesis of one utterance → WAV bytes.
    Models and voice-states are cached for the server's lifetime."""
    import io

    import soundfile as sf
    from pocket_tts import TTSModel

    with _PREVIEW_LOCK:
        model = _PREVIEW_CACHE.get("pocket-model")
        if model is None:
            model = TTSModel.load_model()
            _PREVIEW_CACHE["pocket-model"] = model
        state_key = (
            f"pocket-state:ref:{ref}" if ref else f"pocket-state:{voice}"
        )
        voice_state = _PREVIEW_CACHE.get(state_key)
        if voice_state is None:
            prompt = str(ref) if ref else voice
            voice_state = model.get_state_for_audio_prompt(prompt)
            _PREVIEW_CACHE[state_key] = voice_state
        audio = model.generate_audio(voice_state, text)

    buf = io.BytesIO()
    sf.write(buf, audio.numpy(), model.config.mimi.sample_rate
             if hasattr(model.config, "mimi") else 24000, format="WAV")
    return buf.getvalue()


@router.post("/project/voice/preview")
async def preview_voice(body: PreviewRequest) -> Response:
    """Synthesize one short utterance with overrides layered on the
    saved config — powers stock-voice ▶ buttons, clone A/B, and the
    pronunciation listen-check."""
    project = _project_dir()
    config = tts_config_mod.load_or_default(project)

    voice = body.voice or config.voice
    use_ref = (
        body.use_reference
        if body.use_reference is not None
        else (body.voice is None and config.ref_wav is not None)
    )
    ref = (
        tts_config_mod.resolve_ref_wav(project, config) if use_ref else None
    )
    if use_ref and ref is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="no voice reference uploaded yet",
        )

    entries = (
        _entries(body.pronunciations)
        if body.pronunciations is not None
        else config.pronunciations
    )
    text = tts_config_mod.apply_pronunciations(
        body.text or _DEFAULT_PREVIEW_TEXT, entries
    )

    try:
        wav = await asyncio.to_thread(_synthesize_preview, text, voice, ref)
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="pocket-tts isn't installed — run: "
            'pip install "pocket-tts" soundfile',
        ) from exc
    except ValueError as exc:
        # kyutai raises ValueError when the cloning weights are gated.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Voice cloning weights are gated. Accept the terms at "
                "huggingface.co/kyutai/pocket-tts and set HF_TOKEN, "
                f"then retry. ({exc})"
            ),
        ) from exc
    return Response(content=wav, media_type="audio/wav")
