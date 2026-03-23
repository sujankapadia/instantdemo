# InstantDemo

A Claude Code skill that generates narrated demo videos of web applications. Describe what to show, and the skill analyzes your codebase, writes a demo script, and renders an MP4 — no screen recording, no voiceover sessions, no video editing.

## How it works

```
/generate-demo show the signup flow and dashboard
    ↓
Claude Code reads your source — routes, components, page structure
    ↓
Produces a JSON script (Playwright actions + narration)
    ↓
TTS engine → audio clips
Playwright → browser recording
ffmpeg → final MP4
```

The skill walks through five phases with checkpoints at each step so you stay in control:

1. **Understand the product** — reads README, routes, components, seed data, auth
2. **Plan the narrative** — picks a flow, drafts narration, asks for approval
3. **Gather technical details** — finds stable selectors, wait conditions, pacing
4. **Produce the script** — writes a JSON file matching the schema
5. **Validate and render** — checks URLs and selectors, then renders the video

Videos are **regeneratable**. UI changed? Re-run the script. New feature? Add a segment. It's version-controlled JSON, not a frozen screen recording.

## Install

### As a Claude Code plugin

```bash
/plugin marketplace add sujankapadia/instantdemo
/plugin install instantdemo@sujankapadia-instantdemo
```

### Manual install

```bash
git clone https://github.com/sujankapadia/instantdemo.git
cp -r instantdemo/plugins/instantdemo/skills/generate-demo ~/.claude/skills/generate-demo
```

### Prerequisites

```bash
pip install playwright
playwright install chromium
brew install ffmpeg

# TTS provider (pick one)
pip install "kokoro>=0.9.4" soundfile           # Kokoro (local, free, recommended)
pip install google-cloud-sdk                    # Google Cloud TTS
# or set ELEVENLABS_API_KEY in .env             # ElevenLabs (paid)
```

See [TTS-PROVIDERS.md](TTS-PROVIDERS.md) for detailed TTS provider setup. See [docs/kokoro-tts.md](docs/kokoro-tts.md) for Kokoro voices and configuration.

## Usage

In any project with a running web app:

```
/generate-demo show the Active Sessions page and click a session card
```

Or without arguments — the skill explores the codebase and asks which flow to demo:

```
/generate-demo
```

## Origin

Built as a proof of concept inside [claude-code-analytics](https://github.com/sujankapadia/claude-code-analytics), where Claude Code authored the demo pipeline end-to-end by reading frontend source code for selectors, writing narration, and wiring up TTS + Playwright + ffmpeg.
