#!/usr/bin/env python3
"""Render a narrated demo video from a JSON script definition.

Generates a narrated demo video by:
1. Creating TTS audio clips (Piper, Google Cloud, or ElevenLabs)
2. Recording browser interactions with Playwright
3. Merging audio + video with ffmpeg

Usage:
    python render.py script.json --tts google
    python render.py script.json --tts piper --piper-model /path/to/model.onnx
    python render.py script.json --tts elevenlabs --env .env -o demo.mp4
"""

import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from instantdemo.actions import CANONICAL_ACTIONS, validate_segments


# Injected via context.add_init_script — gives the recorded video a
# visible cursor that follows mouse moves and pulses on click.
# Playwright's video recorder doesn't render the OS cursor, so we draw
# our own as a DOM element. Hosted in a closed shadow root to keep it
# out of the page's DOM tree (and away from page scripts that enumerate
# everything). DOMContentLoaded guard avoids running before
# document.documentElement is ready in some navigation timings.
_CURSOR_INJECT_SCRIPT = """
(() => {
  const inject = () => {
    const host = document.createElement('div');
    host.style.cssText = 'position:fixed;top:0;left:0;width:0;height:0;z-index:2147483647;pointer-events:none';
    document.documentElement.appendChild(host);

    const root = host.attachShadow({ mode: 'closed' });
    root.innerHTML = `
      <style>
        .cursor {
          position: fixed;
          top: 0; left: 0;
          width: 14px; height: 14px;
          background: rgba(255, 255, 255, 0.95);
          border: 1.5px solid rgba(20, 20, 20, 0.75);
          border-radius: 50%;
          box-shadow: 0 1px 4px rgba(0, 0, 0, 0.4);
          transform: translate(-100px, -100px);
          transition: transform 0.18s cubic-bezier(0.2, 0.7, 0.3, 1);
          pointer-events: none;
          will-change: transform;
        }
        .cursor.click { animation: pulse 0.4s ease-out; }
        @keyframes pulse {
          0%   { box-shadow: 0 0 0 0 rgba(58, 162, 255, 0.6); }
          100% { box-shadow: 0 0 0 24px rgba(58, 162, 255, 0); }
        }
      </style>
      <div class="cursor" id="cur"></div>
    `;
    const cur = root.getElementById('cur');

    document.addEventListener('mousemove', (e) => {
      cur.style.transform = `translate(${e.clientX - 7}px, ${e.clientY - 7}px)`;
    }, true);
    document.addEventListener('mousedown', () => {
      cur.classList.remove('click');
      void cur.offsetWidth;  // restart animation
      cur.classList.add('click');
    }, true);
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', inject);
  } else {
    inject();
  }
})();
"""


# ---------------------------------------------------------------------------
# Environment loading
# ---------------------------------------------------------------------------


def _load_env(env_path: Path) -> dict[str, str]:
    """Load key=value pairs from an .env file."""
    env = {}
    if not env_path.exists():
        return env
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip()
    return env


# ---------------------------------------------------------------------------
# TTS Providers
# ---------------------------------------------------------------------------


def _silent_clip(tmp_dir: Path, index: int) -> Path:
    """Generate a minimal silent WAV clip for segments with no narration."""
    output_path = tmp_dir / f"segment_{index}_silent.wav"
    subprocess.run(  # nosec B607
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i",
            "anullsrc=r=44100:cl=stereo", "-t", "0.1",
            str(output_path),
        ],
        capture_output=True,
    )
    return output_path


def generate_audio_piper(
    segments: list[dict], tmp_dir: Path, piper_model: str
) -> list[Path]:
    """Generate WAV audio clips using Piper TTS (local, offline)."""
    clips = []
    for i, seg in enumerate(segments):
        text = seg["narration"]
        if not text.strip():
            clips.append(_silent_clip(tmp_dir, i))
            print(f"  Segment {i}: empty narration, using silence")
            continue
        output_path = tmp_dir / f"segment_{i}.wav"
        print(f"  Generating audio for segment {i}: {text[:50]}...")
        result = subprocess.run(  # nosec B607
            ["piper", "--model", piper_model, "--output_file", str(output_path)],
            input=text,
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            print(f"  Piper error: {result.stderr}", file=sys.stderr)
            sys.exit(1)
        clips.append(output_path)
    return clips


def generate_audio_google(
    segments: list[dict], tmp_dir: Path, env_path: Path
) -> list[Path]:
    """Generate WAV audio clips using Google Cloud TTS (WaveNet)."""
    env = _load_env(env_path)
    project = env.get("GCP_PROJECT") or os.environ.get("GCP_PROJECT")
    if not project:
        print(
            "  Set GCP_PROJECT in .env or your environment",
            file=sys.stderr,
        )
        sys.exit(1)
    voice = env.get("GCP_VOICE", os.environ.get("GCP_VOICE", "en-US-WaveNet-D"))
    language = env.get("GCP_LANGUAGE", os.environ.get("GCP_LANGUAGE", "en-US"))

    # Get access token from gcloud CLI
    result = subprocess.run(  # nosec B607
        ["gcloud", "auth", "print-access-token"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"  gcloud auth error: {result.stderr}", file=sys.stderr)
        print("  Run: gcloud auth login", file=sys.stderr)
        sys.exit(1)
    access_token = result.stdout.strip()

    api_url = "https://texttospeech.googleapis.com/v1/text:synthesize"
    clips = []
    for i, seg in enumerate(segments):
        text = seg["narration"]
        if not text.strip():
            clips.append(_silent_clip(tmp_dir, i))
            print(f"  Segment {i}: empty narration, using silence")
            continue
        output_path = tmp_dir / f"segment_{i}.wav"
        print(f"  Generating audio for segment {i}: {text[:50]}...")

        request_body = json.dumps(
            {
                "input": {"text": text},
                "voice": {"languageCode": language, "name": voice},
                "audioConfig": {"audioEncoding": "LINEAR16"},
            }
        ).encode()

        req = urllib.request.Request(
            api_url,
            data=request_body,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "x-goog-user-project": project,
            },
        )
        try:
            with urllib.request.urlopen(req) as resp:  # nosec B310
                data = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            print(f"  Google TTS error ({e.code}): {body}", file=sys.stderr)
            sys.exit(1)

        audio_bytes = base64.b64decode(data["audioContent"])
        output_path.write_bytes(audio_bytes)
        clips.append(output_path)
    return clips


def generate_audio_elevenlabs(
    segments: list[dict], tmp_dir: Path, env_path: Path
) -> list[Path]:
    """Generate MP3 audio clips using ElevenLabs TTS."""
    env = _load_env(env_path)
    api_key = env.get("ELEVENLABS_API_KEY") or os.environ.get("ELEVENLABS_API_KEY", "")
    voice_id = env.get("ELEVENLABS_VOICE_ID") or os.environ.get(
        "ELEVENLABS_VOICE_ID", ""
    )
    if not api_key or not voice_id:
        print(
            "  Set ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID in .env or environment",
            file=sys.stderr,
        )
        sys.exit(1)

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    clips = []
    for i, seg in enumerate(segments):
        text = seg["narration"]
        if not text.strip():
            clips.append(_silent_clip(tmp_dir, i))
            print(f"  Segment {i}: empty narration, using silence")
            continue
        output_path = tmp_dir / f"segment_{i}.mp3"
        print(f"  Generating audio for segment {i}: {text[:50]}...")

        request_body = json.dumps(
            {
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {
                    "stability": float(
                        env.get("ELEVENLABS_STABILITY", "0.5")
                    ),
                    "similarity_boost": float(
                        env.get("ELEVENLABS_SIMILARITY_BOOST", "0.75")
                    ),
                    "style": float(env.get("ELEVENLABS_STYLE", "0.0")),
                    "use_speaker_boost": env.get(
                        "ELEVENLABS_USE_SPEAKER_BOOST", "true"
                    ).lower()
                    == "true",
                },
            }
        ).encode()

        req = urllib.request.Request(
            url,
            data=request_body,
            headers={
                "xi-api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
        )
        try:
            with urllib.request.urlopen(req) as resp:  # nosec B310
                output_path.write_bytes(resp.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            print(f"  ElevenLabs error ({e.code}): {body}", file=sys.stderr)
            sys.exit(1)

        clips.append(output_path)
    return clips


def generate_audio_kokoro(
    segments: list[dict], tmp_dir: Path, voice: str, speed: float
) -> list[Path]:
    """Generate WAV audio clips using Kokoro TTS (local, high quality, fast)."""
    try:
        import soundfile as sf
        from kokoro import KPipeline
    except ImportError:
        print(
            "  Kokoro not installed. Run: pip install 'kokoro>=0.9.4' soundfile",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"  Loading Kokoro model (voice={voice}, speed={speed})...")
    pipeline = KPipeline(lang_code=voice[0])  # first char is language code

    clips = []
    for i, seg in enumerate(segments):
        text = seg["narration"]
        if not text.strip():
            clips.append(_silent_clip(tmp_dir, i))
            print(f"  Segment {i}: empty narration, using silence")
            continue
        output_path = tmp_dir / f"segment_{i}.wav"
        print(f"  Generating audio for segment {i}: {text[:50]}...")
        for _gs, _ps, audio in pipeline(text, voice=voice, speed=speed):
            sf.write(str(output_path), audio, 24000)
            break  # one sentence per segment, take the first chunk
        clips.append(output_path)
    return clips


# ---------------------------------------------------------------------------
# Audio / Video utilities
# ---------------------------------------------------------------------------


def get_audio_duration(path: Path) -> float:
    """Get duration of an audio file in seconds using ffprobe."""
    result = subprocess.run(  # nosec B607
        [
            "ffprobe",
            "-v",
            "quiet",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def _write_segment_timing(
    state_dir: Path,
    segments: list[dict],
    audio_durations_s: list[float],
    output_filename: str,
    recorded_durations_s: list[float] | None = None,
) -> None:
    """Write per-segment playback timing to <state_dir>/segment-timing.json.

    Mirrors the timing math used in record_browser_video: each segment's
    duration is max(audio_duration, pause_after_ms / 1000), starts at the
    cumulative end of prior segments. Used by the GUI to map segments
    onto positions in the rendered video for click-to-seek.

    When `recorded_durations_s` is provided (clean-window lengths from
    `record_browser_video`), each segment also gets
    `recorded_clean_duration_s` — the actual length of visible frames
    captured for that segment in the source recording. This is what
    post-render operations (delete-segment, pace tweak, overflow
    detection) need to make frame-accurate cuts into demo.mp4 without
    re-recording. See issue #19.
    """
    cursor = 0.0
    out_segments = []
    for i, seg in enumerate(segments):
        audio_s = audio_durations_s[i]
        pause_s = (seg.get("pause_after_ms") or 0) / 1000
        seg_s = max(audio_s, pause_s)
        entry = {
            "index": i,
            "start_s": round(cursor, 3),
            "end_s": round(cursor + seg_s, 3),
            "audio_duration_s": round(audio_s, 3),
        }
        if recorded_durations_s is not None:
            entry["recorded_clean_duration_s"] = round(
                recorded_durations_s[i], 3
            )
        out_segments.append(entry)
        cursor += seg_s

    state_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "video": output_filename,
        "total_duration_s": round(cursor, 3),
        "segments": out_segments,
    }
    (state_dir / "segment-timing.json").write_text(
        json.dumps(payload, indent=2) + "\n"
    )


def _build_combined_audio(
    audio_clips: list[Path],
    clip_durations: list[float],
    segments: list[dict],
    tmp_dir: Path,
) -> Path:
    """Concat per-segment audio clips with silence padding, return path
    to the combined WAV. Same logic as the combine_audio_video tail —
    extracted so audio-only re-render can reuse it without going through
    video trim+concat."""
    wav_clips = [_ensure_wav(clip, i, tmp_dir) for i, clip in enumerate(audio_clips)]
    audio_files: list[Path] = []
    for i, wav in enumerate(wav_clips):
        audio_files.append(wav)
        pause_ms = segments[i].get("pause_after_ms", 0)
        audio_ms = clip_durations[i] * 1000
        gap_ms = max(0, max(audio_ms, pause_ms) - audio_ms)
        if gap_ms > 0:
            gap_silence = tmp_dir / f"silence_{i}.wav"
            subprocess.run(  # nosec B607
                [
                    "ffmpeg", "-y",
                    "-f", "lavfi",
                    "-i", "anullsrc=r=44100:cl=stereo",
                    "-t", str(gap_ms / 1000),
                    str(gap_silence),
                ],
                capture_output=True,
            )
            audio_files.append(gap_silence)

    combined_audio = tmp_dir / "combined_audio.wav"
    audio_inputs: list[str] = []
    for path in audio_files:
        audio_inputs.extend(["-i", str(path)])
    n = len(audio_files)
    audio_filter = (
        "".join(f"[{i}:a]" for i in range(n))
        + f"concat=n={n}:v=0:a=1[out]"
    )
    subprocess.run(  # nosec B607
        ["ffmpeg", "-y"] + audio_inputs + [
            "-filter_complex", audio_filter,
            "-map", "[out]",
            str(combined_audio),
        ],
        capture_output=True,
    )
    return combined_audio


def cut_segment_from_video(
    existing_video: Path,
    cut_start_s: float,
    cut_end_s: float,
    output_path: Path,
) -> None:
    """Re-encode an mp4 with the frame range [cut_start_s, cut_end_s] removed.

    Uses ffmpeg's `trim` + `concat` filter graph in a single invocation so
    the cut is frame-accurate (vs. `-c:v copy -ss` which only cuts at
    keyframes and can glitch by hundreds of ms).

    Strips audio — callers are expected to mux fresh audio over the
    output via `remux_audio_only` since the original audio also gets cut
    and no longer aligns with anything.

    Trade-off: re-encoding makes a delete-segment operation roughly as
    expensive as a Phase 5 render on the trimmed length. For typical
    1–2 minute demos this is ~10–30s, which is acceptable for a
    once-per-demo surgical action. Caller should run this off the event
    loop. See issue #13.
    """
    filter_graph = (
        f"[0:v]trim=start=0:end={cut_start_s},setpts=PTS-STARTPTS[v0];"
        f"[0:v]trim=start={cut_end_s},setpts=PTS-STARTPTS[v1];"
        f"[v0][v1]concat=n=2:v=1:a=0[outv]"
    )
    result = subprocess.run(  # nosec B607
        [
            "ffmpeg", "-y",
            "-i", str(existing_video),
            "-filter_complex", filter_graph,
            "-map", "[outv]",
            "-c:v", "libx264",
            "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-an",
            str(output_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg cut failed: {result.stderr}")


def remux_audio_only(
    existing_video: Path,
    audio_clips: list[Path],
    clip_durations: list[float],
    segments: list[dict],
    output_path: Path,
    tmp_dir: Path,
    recorded_durations_s: list[float] | None = None,
) -> None:
    """Replace the audio track of an existing demo.mp4 with newly-built
    audio. Picks one of three strategies based on how the new audio
    compares to the existing per-segment video:

    1. **No overflow anywhere** → fastest path: `-c:v copy`, just swap
       the audio track.
    2. **Per-segment overflow** (some segment's new audio is longer
       than its recorded clean video) → rebuild the video by trimming
       each segment from `existing_video`, extending overflowing ones
       with `tpad` (frozen last frame), concatenating, then muxing.
       Requires `recorded_durations_s`. See issue #37.
    3. **Global tail overflow** (total audio > total video, but we
       don't have per-segment durations to know where) → tpad the
       last frame of the whole video. Same one-shot pad we used
       before per-segment was an option.

    `recorded_durations_s` is the per-segment clean video durations
    persisted by #19. When provided, we can detect and fix overflow
    surgically; otherwise we fall back to the global tail pad.
    """
    combined_audio = _build_combined_audio(
        audio_clips, clip_durations, segments, tmp_dir
    )

    # Compute per-segment slot durations (matches _build_combined_audio's
    # logic: each segment occupies max(audio, pause) of the timeline).
    slot_durations_s = [
        max(clip_durations[i], (segments[i].get("pause_after_ms") or 0) / 1000)
        for i in range(len(segments))
    ]

    # If we have per-segment recorded durations, we can do surgical
    # per-segment extension. Detect overflow per segment.
    if recorded_durations_s is not None and len(recorded_durations_s) == len(segments):
        per_seg_overflow = [
            slot_durations_s[i] - recorded_durations_s[i]
            for i in range(len(segments))
        ]
        if any(p > 0.05 for p in per_seg_overflow):
            _remux_with_per_segment_extension(
                existing_video=existing_video,
                combined_audio=combined_audio,
                recorded_durations_s=recorded_durations_s,
                slot_durations_s=slot_durations_s,
                output_path=output_path,
            )
            return
        # All segments fit — use cheap copy path below.

    audio_duration = get_audio_duration(combined_audio)
    video_duration = get_audio_duration(existing_video)
    pad_seconds = audio_duration - video_duration

    if pad_seconds > 0.05:
        print(
            f"  Audio longer than video by {pad_seconds:.2f}s; "
            f"freezing last frame to match (re-encoding)…"
        )
        result = subprocess.run(  # nosec B607
            [
                "ffmpeg", "-y",
                "-i", str(existing_video),
                "-i", str(combined_audio),
                "-filter_complex",
                f"[0:v]tpad=stop_mode=clone:stop_duration={pad_seconds:.3f}[vpad]",
                "-map", "[vpad]",
                "-map", "1:a",
                "-c:v", "libx264",
                "-preset", "fast",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "192k",
                str(output_path),
            ],
            capture_output=True,
            text=True,
        )
    else:
        print("  Re-muxing existing video with new audio (no re-encode)…")
        result = subprocess.run(  # nosec B607
            [
                "ffmpeg", "-y",
                "-i", str(existing_video),
                "-i", str(combined_audio),
                "-map", "0:v",
                "-map", "1:a",
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
                str(output_path),
            ],
            capture_output=True,
            text=True,
        )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg remux failed: {result.stderr}")


def _remux_with_per_segment_extension(
    existing_video: Path,
    combined_audio: Path,
    recorded_durations_s: list[float],
    slot_durations_s: list[float],
    output_path: Path,
) -> None:
    """Rebuild the video with per-segment trim + tpad-extend + concat,
    then mux the new audio. Used when at least one segment's audio
    grew past its recorded video frames. See issue #37."""
    # Cut points: segment N's clean window in existing_video occupies
    # [sum(recorded[0..N-1]), sum(recorded[0..N])]. Each segment is
    # then padded so its output duration matches its audio slot.
    cursor = 0.0
    trim_clauses: list[str] = []
    pad_clauses: list[str] = []
    concat_inputs: list[str] = []
    for i, (rec, slot) in enumerate(zip(recorded_durations_s, slot_durations_s)):
        start = cursor
        end = cursor + rec
        cursor = end
        # Trim segment i from the source video and reset its timestamps.
        trim_clauses.append(
            f"[0:v]trim=start={start:.3f}:end={end:.3f},"
            f"setpts=PTS-STARTPTS[s{i}t]"
        )
        # If this segment overflows, freeze the last frame for the
        # missing duration. Otherwise pass through unchanged.
        pad = max(0.0, slot - rec)
        if pad > 0.05:
            pad_clauses.append(
                f"[s{i}t]tpad=stop_mode=clone:stop_duration={pad:.3f}[s{i}]"
            )
        else:
            pad_clauses.append(f"[s{i}t]null[s{i}]")
        concat_inputs.append(f"[s{i}]")

    filter_graph = (
        ";".join(trim_clauses)
        + ";"
        + ";".join(pad_clauses)
        + ";"
        + "".join(concat_inputs)
        + f"concat=n={len(recorded_durations_s)}:v=1:a=0[outv]"
    )

    total_pad = sum(max(0.0, s - r) for r, s in zip(recorded_durations_s, slot_durations_s))
    print(
        f"  Per-segment overflow detected ({total_pad:.2f}s total); "
        f"rebuilding video with extended segments (re-encoding)…"
    )
    result = subprocess.run(  # nosec B607
        [
            "ffmpeg", "-y",
            "-i", str(existing_video),
            "-i", str(combined_audio),
            "-filter_complex", filter_graph,
            "-map", "[outv]",
            "-map", "1:a",
            "-c:v", "libx264",
            "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            str(output_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg per-segment remux failed: {result.stderr}")


def _ensure_wav(clip: Path, index: int, tmp_dir: Path) -> Path:
    """Convert an audio clip to WAV if it isn't already."""
    if clip.suffix == ".wav":
        return clip
    wav_path = tmp_dir / f"segment_{index}.wav"
    subprocess.run(  # nosec B607
        ["ffmpeg", "-y", "-i", str(clip), str(wav_path)],
        capture_output=True,
    )
    return wav_path


# ---------------------------------------------------------------------------
# Action dispatch
# ---------------------------------------------------------------------------

def _selector_candidates(value) -> list[str]:
    """Normalize a selector field into a list of candidates. Accepts:
    - a single string (returns [that string])
    - a list of strings (filters out empties)
    - None / empty (returns [])

    See issue #47 — Phase 3 lists fallbacks; Phase 4 emits them as a
    list; renderer iterates here.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return [s for s in value if isinstance(s, str) and s]
    if isinstance(value, str) and value:
        return [value]
    return []


def _wait_first_match(page, selectors: list[str], *, total_timeout_ms: int = 10000) -> str:
    """Try each selector in order; return the first that resolves. The
    total_timeout_ms is divided across candidates (with a 2s minimum
    per candidate) so a 3-fallback case can't stall for 30s.

    Raises the last selector's error if none resolve.
    """
    if not selectors:
        raise RuntimeError("no selector candidates")
    per = max(2000, total_timeout_ms // len(selectors))
    last_err: Exception | None = None
    for sel in selectors:
        try:
            page.wait_for_selector(sel, timeout=per)
            return sel
        except Exception as e:
            last_err = e
    if last_err is not None:
        raise last_err
    raise RuntimeError("unreachable")


def _action_click(page, seg: dict) -> None:
    matched = _wait_first_match(page, _selector_candidates(seg["selector"]))
    _glide_to(page, matched)
    page.click(matched)


def _action_fill(page, seg: dict) -> None:
    matched = _wait_first_match(page, _selector_candidates(seg["selector"]))
    _glide_to(page, matched)
    page.fill(matched, seg["value"])


def _action_hover(page, seg: dict) -> None:
    matched = _wait_first_match(page, _selector_candidates(seg["selector"]))
    _glide_to(page, matched)
    page.hover(matched)


# Known actions with explicit argument mapping. Actions not listed here
# fall back to getattr(page, action) with segment fields as kwargs.
_ACTION_FIELD_MAP = {
    "navigate": lambda page, seg: _action_navigate(page, seg),
    "goto": lambda page, seg: _action_navigate(page, seg),
    "click": _action_click,
    "fill": _action_fill,
    "hover": _action_hover,
    "scroll": lambda page, seg: _action_scroll(page, seg),
    "wait": lambda _page, _seg: None,
    "select_option": lambda page, seg: page.select_option(
        seg["selector"], seg["value"]
    ),
    "press": lambda page, seg: page.press(seg["selector"], seg["key"]),
    "check": lambda page, seg: page.check(seg["selector"]),
    "uncheck": lambda page, seg: page.uncheck(seg["selector"]),
    "evaluate": lambda page, seg: page.evaluate(seg["expression"]),
}

# The dispatch table and the shared contract (actions.py) must agree —
# a new action added to one without the other should fail at import,
# not at render time.
assert set(_ACTION_FIELD_MAP) == set(CANONICAL_ACTIONS), (
    "render._ACTION_FIELD_MAP and actions.CANONICAL_ACTIONS disagree: "
    f"{set(_ACTION_FIELD_MAP) ^ set(CANONICAL_ACTIONS)}"
)


def _parse_resolution(text: str) -> dict:
    """argparse type that turns 'WxH' into {'width': W, 'height': H}.

    Accepts both 'x' and 'X' as the separator. Rejects non-positive
    integers and obviously-bogus values so users see the error at
    parse time rather than mid-render.
    """
    raw = text.strip().lower()
    parts = raw.replace("X", "x").split("x")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(
            f"resolution must be WIDTHxHEIGHT (e.g. 1920x1080), got {text!r}"
        )
    try:
        width, height = int(parts[0]), int(parts[1])
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"resolution dimensions must be integers, got {text!r}"
        )
    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError(
            f"resolution dimensions must be positive, got {text!r}"
        )
    return {"width": width, "height": height}


def _glide_to(page, selector: str, steps: int = 24) -> None:
    """Move the mouse to the selector's center with intermediate steps so
    the injected cursor visibly glides instead of teleporting. No-op if
    the selector isn't resolvable to a bounding box (off-screen, hidden,
    etc.) — the subsequent action still runs and Playwright's internal
    move handles correctness."""
    try:
        box = page.locator(selector).bounding_box(timeout=2000)
    except Exception:
        return
    if not box:
        return
    cx = box["x"] + box["width"] / 2
    cy = box["y"] + box["height"] / 2
    page.mouse.move(cx, cy, steps=steps)
    time.sleep(0.2)  # let the cursor settle before the action fires


def _action_navigate(page, seg: dict) -> None:
    """Handle navigate/goto action with optional wait_for selector(s).

    `wait_for` may be a string or a list of fallback selectors. The
    first that resolves wins. See issue #47.
    """
    page.goto(seg["url"], wait_until="domcontentloaded")
    wait_candidates = _selector_candidates(seg.get("wait_for"))
    if wait_candidates:
        _wait_first_match(page, wait_candidates, total_timeout_ms=15000)
    else:
        page.wait_for_load_state("load")
        time.sleep(1)


def _action_scroll(page, seg: dict) -> None:
    """Handle scroll action with smooth behavior."""
    pixels = seg.get("pixels", 300)
    page.evaluate(
        f"window.scrollBy({{ top: {pixels}, behavior: 'smooth' }})"
    )
    # Give the smooth scroll animation time to complete
    time.sleep(min(abs(pixels) / 500, 1.5))


def _dispatch_action(page, seg: dict) -> None:
    """Dispatch a segment's action to the appropriate Playwright method.

    Unknown actions are a hard error. There used to be a fallback
    that called `getattr(page, action)` with the segment's
    non-reserved fields as kwargs — but _RESERVED_FIELDS strips
    exactly the fields (selector, url, value, ...) that such methods
    require, so the fallback crashed mid-recording for the very
    actions it existed to support (e.g. an agent-improvised
    `wait_for_selector`). The action set is closed now; `main()`
    validates segments up front, so reaching this error means a
    caller bypassed validation.
    """
    action = seg["action"]
    handler = _ACTION_FIELD_MAP.get(action)
    if handler is None:
        raise ValueError(
            f"Unknown action {action!r}; allowed: "
            f"{', '.join(sorted(_ACTION_FIELD_MAP))}"
        )
    handler(page, seg)


# ---------------------------------------------------------------------------
# Browser recording
# ---------------------------------------------------------------------------


def record_browser_video(
    segments: list[dict],
    clip_durations: list[float],
    resolution: dict,
    tmp_dir: Path,
) -> tuple[Path, list[tuple[float, float]]]:
    """Record browser interactions with video capture, tracking segment timestamps.

    Returns (video_path, timestamps) where timestamps is a list of
    (start, end) pairs in seconds relative to the recording start.
    Each start marks when the action completed (page ready, no loading),
    and end marks when the segment sleep finished.
    """
    from playwright.sync_api import sync_playwright

    video_path = None
    timestamps = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport={
                "width": resolution["width"],
                "height": resolution["height"],
            },
            record_video_dir=str(tmp_dir),
            record_video_size={
                "width": resolution["width"],
                "height": resolution["height"],
            },
        )
        context.add_init_script(_CURSOR_INJECT_SCRIPT)
        page = context.new_page()
        recording_start = time.monotonic()

        for i, seg in enumerate(segments):
            action = seg["action"]
            pause_ms = seg.get("pause_after_ms", 0)
            audio_duration_ms = clip_durations[i] * 1000
            wait_ms = max(audio_duration_ms, pause_ms)

            print(f"  Segment {i}: action={action}, wait={wait_ms:.0f}ms")

            _dispatch_action(page, seg)

            # Action complete, page is ready — mark the clean start
            seg_start = time.monotonic() - recording_start

            # Wait for the duration of the narration + any extra pause
            time.sleep(wait_ms / 1000)

            seg_end = time.monotonic() - recording_start
            timestamps.append((seg_start, seg_end))

        # Close context to finalize video
        video = page.video
        if video is None:
            print("Error: no video was recorded", file=sys.stderr)
            sys.exit(1)
        video_path = video.path()
        context.close()
        browser.close()

    return Path(video_path), timestamps


# ---------------------------------------------------------------------------
# Audio + video merge
# ---------------------------------------------------------------------------


def combine_audio_video(
    video_path: Path,
    audio_clips: list[Path],
    clip_durations: list[float],
    segments: list[dict],
    output_path: Path,
    tmp_dir: Path,
    timestamps: list[tuple[float, float]],
) -> None:
    """Merge audio clips with video into final MP4 using ffmpeg.

    Uses segment timestamps to trim loading frames from the video before
    merging with audio. Each segment's video is extracted from the continuous
    recording starting when the action completed (page ready), excluding
    any loading/skeleton frames that preceded it.
    """
    # Normalize all clips to WAV for consistent concatenation
    wav_clips = [_ensure_wav(clip, i, tmp_dir) for i, clip in enumerate(audio_clips)]

    # Build the ordered list of audio files (per-segment audio + gap silences).
    audio_files: list[Path] = []
    for i, wav in enumerate(wav_clips):
        audio_files.append(wav)
        pause_ms = segments[i].get("pause_after_ms", 0)
        audio_ms = clip_durations[i] * 1000
        gap_ms = max(0, max(audio_ms, pause_ms) - audio_ms)
        if gap_ms > 0:
            gap_silence = tmp_dir / f"silence_{i}.wav"
            subprocess.run(  # nosec B607
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "anullsrc=r=44100:cl=stereo",
                    "-t",
                    str(gap_ms / 1000),
                    str(gap_silence),
                ],
                capture_output=True,
            )
            audio_files.append(gap_silence)

    # Concatenate via filter_complex `concat` rather than the concat demuxer
    # with `-c copy`. The demuxer doesn't normalize formats — when the
    # silence helpers (44100 stereo) are mixed with a TTS provider that
    # outputs a different format (e.g. Kokoro at 24000 mono), the output
    # WAV header takes the first file's format and downstream byte counts
    # produce a wildly wrong duration. filter_complex resamples to a common
    # format and produces correct-duration output.
    combined_audio = tmp_dir / "combined_audio.wav"
    audio_inputs: list[str] = []
    for path in audio_files:
        audio_inputs.extend(["-i", str(path)])
    n = len(audio_files)
    audio_filter = (
        "".join(f"[{i}:a]" for i in range(n))
        + f"concat=n={n}:v=0:a=1[out]"
    )
    subprocess.run(  # nosec B607
        ["ffmpeg", "-y"] + audio_inputs + [
            "-filter_complex",
            audio_filter,
            "-map",
            "[out]",
            str(combined_audio),
        ],
        capture_output=True,
    )

    # Trim, concatenate, and mux in a single ffmpeg pass
    # This decodes the source WebM once, trims segments in memory,
    # concatenates them, and encodes to H.264 exactly once.
    print("  Trimming segments and merging with audio...")
    filter_parts = []
    for i, (seg_start, seg_end) in enumerate(timestamps):
        duration = seg_end - seg_start
        filter_parts.append(
            f"[0:v]trim=start={seg_start:.3f}:duration={duration:.3f},"
            f"setpts=PTS-STARTPTS[v{i}]"
        )
    concat_inputs = "".join(f"[v{i}]" for i in range(len(timestamps)))
    filter_parts.append(
        f"{concat_inputs}concat=n={len(timestamps)}:v=1:a=0[outv]"
    )
    filter_complex = ";".join(filter_parts)

    result = subprocess.run(  # nosec B607
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(combined_audio),
            "-filter_complex",
            filter_complex,
            "-map",
            "[outv]",
            "-map",
            "1:a",
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-preset",
            "slow",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            str(output_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"  ffmpeg error: {result.stderr}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="instantdemo render",
        description="Render a narrated demo video from a JSON script definition",
    )
    parser.add_argument(
        "script",
        type=Path,
        help="Path to the demo script JSON file",
    )
    parser.add_argument(
        "--tts",
        choices=["piper", "google", "elevenlabs", "kokoro"],
        default="google",
        help="TTS provider (default: google)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output MP4 path (default: <script-stem>-demo.mp4 in CWD)",
    )
    parser.add_argument(
        "--env",
        type=Path,
        default=None,
        help="Path to .env file for TTS credentials (default: .env in CWD)",
    )
    parser.add_argument(
        "--piper-model",
        type=str,
        default=None,
        help="Path to Piper ONNX model (or set PIPER_MODEL_PATH env var)",
    )
    parser.add_argument(
        "--kokoro-voice",
        type=str,
        default="af_heart",
        help="Kokoro voice name (default: af_heart). See docs/kokoro-tts.md for full list.",
    )
    parser.add_argument(
        "--kokoro-speed",
        type=float,
        default=1.0,
        help="Kokoro speech speed (default: 1.0)",
    )
    parser.add_argument(
        "--resolution",
        type=_parse_resolution,
        default=None,
        metavar="WxH",
        help="Override the script's resolution (e.g. 1920x1080). "
        "Default: 1920x1080 if the script doesn't specify a resolution.",
    )
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=None,
        help="Directory to write segment-timing.json (default: <script>/.instantdemo)",
    )
    args = parser.parse_args(argv)

    # Resolve paths
    script_path = args.script.resolve()
    if not script_path.exists():
        print(f"Script not found: {script_path}", file=sys.stderr)
        sys.exit(1)

    output_path = (
        args.output.resolve()
        if args.output
        else Path.cwd() / f"{script_path.stem}-demo.mp4"
    )
    env_path = args.env.resolve() if args.env else Path.cwd() / ".env"
    tmp_dir = Path(tempfile.mkdtemp(prefix="instantdemo-"))

    print(f"Script:  {script_path}")
    print(f"Output:  {output_path}")
    print(f"Tmp dir: {tmp_dir}")
    print()

    script = json.loads(script_path.read_text())
    segments = script["segments"]

    # Validate the action contract before spending anything — a bad
    # segment caught here costs nothing; caught mid-recording it
    # costs the whole single-take video (and the TTS run before it).
    # Phase 5 validates too, but hand-edited scripts come straight
    # here.
    problems = validate_segments(segments)
    if problems:
        print("Error: demo script failed validation:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        sys.exit(1)

    # Resolution priority: --resolution flag > script's "resolution" field > 1920x1080 default
    if args.resolution is not None:
        resolution = args.resolution
    elif "resolution" in script:
        resolution = script["resolution"]
    else:
        resolution = {"width": 1920, "height": 1080}
    print(f"Resolution: {resolution['width']}x{resolution['height']}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Phase A: Generate audio clips
    provider_name = args.tts
    print(f"Phase A: Generating audio clips with {provider_name}...")
    if provider_name == "piper":
        piper_model = args.piper_model or os.environ.get("PIPER_MODEL_PATH")
        if not piper_model:
            print(
                "  Set --piper-model or PIPER_MODEL_PATH env var",
                file=sys.stderr,
            )
            sys.exit(1)
        audio_clips = generate_audio_piper(segments, tmp_dir, piper_model)
    elif provider_name == "google":
        audio_clips = generate_audio_google(segments, tmp_dir, env_path)
    elif provider_name == "elevenlabs":
        audio_clips = generate_audio_elevenlabs(segments, tmp_dir, env_path)
    elif provider_name == "kokoro":
        audio_clips = generate_audio_kokoro(
            segments, tmp_dir, args.kokoro_voice, args.kokoro_speed
        )
    else:
        print(f"  Unknown TTS provider: {provider_name}", file=sys.stderr)
        sys.exit(1)

    clip_durations = [get_audio_duration(clip) for clip in audio_clips]
    for i, dur in enumerate(clip_durations):
        print(f"  Segment {i} audio: {dur:.2f}s")

    # Phase B: Record browser video
    print("\nPhase B: Recording browser with Playwright...")
    video_path, timestamps = record_browser_video(
        segments, clip_durations, resolution, tmp_dir
    )
    print(f"  Video saved: {video_path}")

    # Phase C: Combine audio + video
    print("\nPhase C: Combining audio + video with ffmpeg...")
    combine_audio_video(
        video_path, audio_clips, clip_durations, segments, output_path, tmp_dir,
        timestamps,
    )

    # Phase D: Write per-segment timing for the GUI segments view
    state_dir = (
        args.state_dir.resolve()
        if args.state_dir
        else script_path.parent / ".instantdemo"
    )
    recorded_durations = [end - start for (start, end) in timestamps]
    _write_segment_timing(
        state_dir, segments, clip_durations, output_path.name,
        recorded_durations_s=recorded_durations,
    )
    print(f"  Timing: {state_dir / 'segment-timing.json'}")

    print(f"\nDone! Output: {output_path}")
    print(f"Temp files at: {tmp_dir}")


if __name__ == "__main__":
    main()
