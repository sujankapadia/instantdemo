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

## Key differentiator

Videos are **regeneratable**. Traditional screen recordings are frozen in time — one UI change and you re-record, re-narrate, re-edit. InstantDemo scripts are code: version them, parameterize them, re-run them.

## Origin

Built as a proof-of-concept inside [claude-code-analytics](https://github.com/sujankapadia/claude-code-analytics), where Claude Code authored the demo pipeline end-to-end: script generation (by reading frontend source for selectors), TTS integration (Piper, Google Cloud, ElevenLabs), Playwright browser recording, and ffmpeg merging. See [PIPELINE.md](PIPELINE.md) for the current pipeline architecture.

## Status

Proof-of-concept pipeline working. Next steps: build the product layer on top.
