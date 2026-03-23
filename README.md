# InstantDemo

Turn words into narrated demo videos of your web app. Describe what to show, get a polished screencast — no screen recording, no voiceover sessions, no video editing.

## Vision

A self-service tool that generates narrated product walkthroughs from natural language descriptions. Videos are regeneratable — ship a UI update, re-run the script, get an updated video in minutes.

## How it works

```
"Show the signup flow, fill the form, land on dashboard"
    ↓
LLM inspects your app → generates a script (selectors + narration)
    ↓
TTS engine → audio clips
Playwright → browser recording
ffmpeg → final MP4
```

## Use cases

- **Developer advocates** — product walkthroughs that stay current with the UI
- **SaaS founders** — landing page videos without re-recording after every release
- **Support teams** — how-to videos generated from help docs
- **Sales engineers** — custom demos per prospect, generated on demand

## Core insight

The hard parts of making a demo video — script authoring, selector discovery, narration writing — are exactly what an LLM is good at. The rendering pipeline (TTS + Playwright + ffmpeg) is fully automatable. Combining the two means no human needs to touch a screen recorder or video editor.

## Key differentiator

Videos are **regeneratable**. Traditional screen recordings are frozen in time — one UI change and you re-record, re-narrate, re-edit. InstantDemo scripts are code: version them, parameterize them, re-run them.

## Product workflow

1. User pastes a URL (or connects their staging env)
2. App crawls the page, builds a DOM map of interactive elements
3. User describes the flow in natural language ("show signup, fill the form, land on dashboard")
4. LLM generates the script JSON (selectors + narration)
5. User previews/edits the script in a visual timeline editor
6. Pipeline renders the video with chosen TTS voice
7. User downloads MP4 or embeds it

## Monetization

Charge per video render, or monthly plan. Primary costs are TTS API usage and compute for browser recording.

## Origin

Built as a proof-of-concept inside [claude-code-analytics](https://github.com/sujankapadia/claude-code-analytics), where Claude Code authored the demo pipeline end-to-end: script generation (by reading frontend source for selectors), TTS integration (Piper, Google Cloud, ElevenLabs), Playwright browser recording, and ffmpeg merging. See [TTS-PROVIDERS.md](TTS-PROVIDERS.md) for TTS provider setup and configuration.

## Using the Skill

InstantDemo is packaged as a Claude Code skill. Install it:

```bash
# Clone the repo
git clone https://github.com/sujankapadia/instantdemo.git

# Copy to your skills directory
cp -r instantdemo/plugins/instantdemo/skills/generate-demo ~/.claude/plugins/instantdemo/skills/generate-demo
```

Then in any project with a running web app:

```
/generate-demo
```

The skill walks you through: codebase analysis → narrative planning → script generation → validation → rendering.

### Prerequisites

```bash
pip install playwright
playwright install chromium
brew install ffmpeg
pip install google-cloud-sdk   # or piper-tts, or set ELEVENLABS_API_KEY
```

### Rendering directly

```bash
python plugins/instantdemo/skills/generate-demo/scripts/render.py script.json --tts google -o demo.mp4
```

## Status

Proof-of-concept pipeline working, packaged as a Claude Code skill.
