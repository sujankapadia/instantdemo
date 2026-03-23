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


def generate_audio_piper(
    segments: list[dict], tmp_dir: Path, piper_model: str
) -> list[Path]:
    """Generate WAV audio clips using Piper TTS (local, offline)."""
    clips = []
    for i, seg in enumerate(segments):
        output_path = tmp_dir / f"segment_{i}.wav"
        text = seg["narration"]
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
        output_path = tmp_dir / f"segment_{i}.wav"
        text = seg["narration"]
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
        output_path = tmp_dir / f"segment_{i}.mp3"
        text = seg["narration"]
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

# Known actions with explicit argument mapping. Actions not listed here
# fall back to getattr(page, action) with segment fields as kwargs.
_ACTION_FIELD_MAP = {
    "navigate": lambda page, seg: _action_navigate(page, seg),
    "goto": lambda page, seg: _action_navigate(page, seg),
    "click": lambda page, seg: (
        page.wait_for_selector(seg["selector"], timeout=10000),
        page.click(seg["selector"]),
    ),
    "fill": lambda page, seg: (
        page.wait_for_selector(seg["selector"], timeout=10000),
        page.fill(seg["selector"], seg["value"]),
    ),
    "hover": lambda page, seg: (
        page.wait_for_selector(seg["selector"], timeout=10000),
        page.hover(seg["selector"]),
    ),
    "scroll": lambda page, seg: _action_scroll(page, seg),
    "wait": lambda _page, _seg: None,
    "select_option": lambda page, seg: page.select_option(
        seg["selector"], seg["value"]
    ),
    "press": lambda page, seg: page.press(seg["selector"], seg["key"]),
    "check": lambda page, seg: page.check(seg["selector"]),
    "uncheck": lambda page, seg: page.uncheck(seg["selector"]),
}

# Fields that are part of the segment schema, not Playwright method args.
_RESERVED_FIELDS = {"narration", "action", "pause_after_ms", "wait_for", "url", "selector", "value", "pixels", "key"}


def _action_navigate(page, seg: dict) -> None:
    """Handle navigate/goto action with optional wait_for selector."""
    page.goto(seg["url"], wait_until="domcontentloaded")
    wait_selector = seg.get("wait_for")
    if wait_selector:
        page.wait_for_selector(wait_selector, timeout=15000)
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
    """Dispatch a segment's action to the appropriate Playwright method."""
    action = seg["action"]
    handler = _ACTION_FIELD_MAP.get(action)
    if handler:
        handler(page, seg)
    else:
        # Fallback: try calling the method directly on page
        method = getattr(page, action, None)
        if method is None:
            print(
                f"  Warning: unknown action '{action}', skipping",
                file=sys.stderr,
            )
            return
        # Pass non-reserved fields as kwargs
        kwargs = {k: v for k, v in seg.items() if k not in _RESERVED_FIELDS}
        method(**kwargs)


# ---------------------------------------------------------------------------
# Browser recording
# ---------------------------------------------------------------------------


def record_browser_video(
    segments: list[dict],
    clip_durations: list[float],
    resolution: dict,
    tmp_dir: Path,
) -> Path:
    """Record browser interactions using Playwright with video capture."""
    from playwright.sync_api import sync_playwright

    video_path = None
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
        page = context.new_page()

        for i, seg in enumerate(segments):
            action = seg["action"]
            pause_ms = seg.get("pause_after_ms", 0)
            audio_duration_ms = clip_durations[i] * 1000
            wait_ms = max(audio_duration_ms, pause_ms)

            print(f"  Segment {i}: action={action}, wait={wait_ms:.0f}ms")

            _dispatch_action(page, seg)

            # Wait for the duration of the narration + any extra pause
            time.sleep(wait_ms / 1000)

        # Close context to finalize video
        video = page.video
        if video is None:
            print("Error: no video was recorded", file=sys.stderr)
            sys.exit(1)
        video_path = video.path()
        context.close()
        browser.close()

    return Path(video_path)


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
) -> None:
    """Merge audio clips with video into final MP4 using ffmpeg."""
    # Normalize all clips to WAV for consistent concatenation
    wav_clips = [_ensure_wav(clip, i, tmp_dir) for i, clip in enumerate(audio_clips)]

    # Build concat list with silence gaps between segments
    concat_list = tmp_dir / "audio_concat.txt"
    entries = []
    for i, wav in enumerate(wav_clips):
        entries.append(f"file '{wav.resolve()}'")
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
            entries.append(f"file '{gap_silence.resolve()}'")

    concat_list.write_text("\n".join(entries))

    # Concatenate all audio clips into a single WAV
    combined_audio = tmp_dir / "combined_audio.wav"
    subprocess.run(  # nosec B607
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-c",
            "copy",
            str(combined_audio),
        ],
        capture_output=True,
    )

    # Merge video + audio into final MP4
    print(f"  Merging video + audio into {output_path}...")
    result = subprocess.run(  # nosec B607
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(combined_audio),
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
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


def main():
    parser = argparse.ArgumentParser(
        description="Render a narrated demo video from a JSON script definition"
    )
    parser.add_argument(
        "script",
        type=Path,
        help="Path to the demo script JSON file",
    )
    parser.add_argument(
        "--tts",
        choices=["piper", "google", "elevenlabs"],
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
    args = parser.parse_args()

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
    resolution = script["resolution"]

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
    else:
        print(f"  Unknown TTS provider: {provider_name}", file=sys.stderr)
        sys.exit(1)

    clip_durations = [get_audio_duration(clip) for clip in audio_clips]
    for i, dur in enumerate(clip_durations):
        print(f"  Segment {i} audio: {dur:.2f}s")

    # Phase B: Record browser video
    print("\nPhase B: Recording browser with Playwright...")
    video_path = record_browser_video(segments, clip_durations, resolution, tmp_dir)
    print(f"  Video saved: {video_path}")

    # Phase C: Combine audio + video
    print("\nPhase C: Combining audio + video with ffmpeg...")
    combine_audio_video(
        video_path, audio_clips, clip_durations, segments, output_path, tmp_dir
    )
    print(f"\nDone! Output: {output_path}")
    print(f"Temp files at: {tmp_dir}")


if __name__ == "__main__":
    main()
