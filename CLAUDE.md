# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

InstantDemo is a proof-of-concept pipeline that generates narrated demo videos from JSON script definitions. It converts UI walkthroughs into MP4 videos by combining TTS audio generation, headless browser recording, and ffmpeg merging.

Extracted from the `claude-code-analytics` project (`github.com/sujankapadia/claude-code-analytics`), where the pipeline was originally built to auto-generate marketing demos. The product idea: give any SaaS a way to generate regeneratable narrated walkthroughs from a URL, without manual screen recording or video editing.

## Claude Code Skill

The project is packaged as a Claude Code skill at `~/.claude/skills/generate-demo/`. Install by copying the skill directory:

```bash
cp -r . ~/.claude/skills/generate-demo/
# Or symlink for development:
ln -s $(pwd) ~/.claude/skills/generate-demo
```

Then use `/generate-demo` in any project to generate a demo video. The skill walks through codebase analysis, narrative planning, script generation, validation, and rendering.

## Running the Renderer Directly

```bash
# Prerequisites
pip install playwright
playwright install chromium
brew install ffmpeg

# TTS provider (pick one)
pip install piper-tts pathvalidate              # Piper (local, free)
pip install google-cloud-sdk                    # Google Cloud TTS
# or set ELEVENLABS_API_KEY in .env             # ElevenLabs (paid)

# Render a script
python scripts/render.py script.json --tts google
python scripts/render.py script.json --tts piper --piper-model /path/to/model.onnx -o demo.mp4
```

Output defaults to `{script-stem}-demo.mp4` in the current directory.

There is no test suite, linter, or build step.

## Architecture

Single-file rendering pipeline (`scripts/render.py`) with three sequential phases:

1. **Audio Generation** — reads the script JSON, runs each segment's narration through the chosen TTS provider, outputs WAV clips to a temp directory
2. **Browser Recording** — Playwright launches Chromium with video recording, executes each segment's action (any Playwright page method), sleeping for `max(audio_duration, pause_after_ms)` to stay in sync
3. **Merge** — ffmpeg concatenates audio clips with silence gaps, then muxes audio + video into the final MP4

TTS providers: `--tts google` (default), `--tts elevenlabs`, `--tts piper`. Actions are open-ended Playwright page methods — `goto`, `click`, `fill`, `hover`, `scroll`, `wait`, etc.

## Demo Script Format

Scripts are JSON files defining the demo flow. See `reference.md` in the skill directory for the full schema. Each segment has:
- `narration` — text spoken by TTS
- `action` — any Playwright `page` method name (`goto`, `click`, `fill`, `hover`, `scroll`, `wait`, etc.)
- Action-specific fields: `url`, `selector`, `value`, `pixels`, `wait_for`, `key`, `pause_after_ms`

## Known Gotchas

- **SSE and `networkidle`**: Playwright's `networkidle` wait state never resolves on pages with Server-Sent Events (SSE). Use `domcontentloaded` + explicit `wait_for_selector` instead.
- **ElevenLabs returns MP3**, not WAV. The merge phase normalizes all clips to WAV before concatenating (ffmpeg concat demuxer with `-c copy` fails on mixed formats).
- **Piper does not auto-download models** by name. Models must be downloaded manually and referenced by local path.
- **ElevenLabs voice settings** (stability, similarity_boost, style, use_speaker_boost) are configurable via `demo/.env`. The current example script was tuned for a cloned voice.
- **Video pacing** is controlled by `pause_after_ms` per segment. If the video feels too fast, increase these values.

## Key External Dependencies

- **Playwright** (`playwright.sync_api`) — browser automation + video capture
- **ffmpeg / ffprobe** — invoked via `subprocess` for audio/video processing
- **TTS CLIs/APIs** — `piper` CLI, `gcloud` CLI (texttospeech), or ElevenLabs REST API

## Origin and Next Steps

The current demo script targets the Active Sessions page of claude-code-analytics (requires that app's API + frontend running on ports 8000/5173). The product vision is to generalize this: given any URL, crawl the DOM, generate a script via LLM, and render a video. See `README.md` for the full product concept and monetization model.
