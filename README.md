# InstantDemo

Generate narrated demo videos of running web apps, automatically. Point it
at a URL, say what you want shown, and InstantDemo explores the live app,
plans a demo, rehearses it against the real thing, then records an MP4 —
no screen recording, no voiceover sessions, no video editing.

Three ways to use it:

- **GUI** (primary) — `instantdemo serve` opens a local app where you watch
  it explore, confirm what the demo should cover, review the storyboard,
  and edit narration inline.
- **CLI** — `instantdemo generate ...` from any terminal.
- **Claude Code skill** — `/generate-demo` inside a Claude Code session.

All three share the same engine (the `instantdemo` Python package) and
produce the same JSON script format.

## How it works

The **live app is the ground truth.** Source code is optional enrichment —
when you provide it, the agent reads it for hidden routes, real feature
names, and actual selectors, but anything source-derived gets verified
against the running app before it's trusted.

Six phases, each reading the previous one's artifact:

```
1. analyze  (Understand) → drives the live app with Playwright, screenshots
                           each screen, proposes what the demo should show
2. narrate  (Plan)       → outlines chapters, writes scene narration
3. gather   (Inspect)    → infers selectors, waits, and pacing per scene
4. explore  (Explore)    → DRESS REHEARSAL: walks every step against the
                           live app and self-corrects — swapping selectors
                           that miss, regrounding narration that overclaims
5. script   (Build)      → deterministic projection to demo-script.json
6. render   (Render)     → Playwright records, TTS narrates, ffmpeg stitches
```

**Phase 4 is the distinctive part.** Rather than generating a script and
hoping it runs, InstantDemo rehearses the whole demo against the real app
first, watches what actually happens at each step, and fixes what it got
wrong before a single frame is recorded. Structural changes (dropping or
reordering scenes) stay blocked and surface to you as suggestions.

Two human gates sit in the flow: you confirm the **proposed intent** after
exploration, and review the **storyboard** before anything renders.

## Install

### Core (CLI + GUI)

```bash
pip install 'instantdemo[gui,pocket-tts]'
playwright install chromium
brew install ffmpeg              # or your platform's equivalent
```

`[pocket-tts]` bundles the default TTS — free, local, CPU-only, with 26
stock voices and optional voice cloning. `[gui]` adds the local web app.
To swap TTS providers later, see [TTS providers](#tts-providers) below.

### Authentication

InstantDemo shells out to the `claude` CLI via `claude-agent-sdk`, so it uses whatever auth `claude` is using. The CLI's precedence is:

1. `ANTHROPIC_API_KEY` env var, if set → bills against your API account
2. Otherwise, the OAuth session from `claude login` → bills against your Claude.ai subscription

The free-via-subscription path is the default. If you have `ANTHROPIC_API_KEY` set for other tools (Cursor, Aider, custom scripts), `instantdemo generate` / `phase` / `serve` will print a startup warning so you don't bill the wrong account silently. To opt back into the subscription:

```bash
unset ANTHROPIC_API_KEY
```

### Claude Code skill (optional)

The skill is a thin wrapper around the same `instantdemo` package — it provides a Claude Code-native conversational UX with `AskUserQuestion`-driven checkpoints. After installing the CLI prerequisites above:

```bash
/plugin marketplace add sujankapadia/instantdemo
/plugin install instantdemo@sujankapadia-instantdemo
```

The skill calls `instantdemo render` under the hood, so the pip install is a hard prerequisite.

## Usage

### GUI (primary)

```bash
instantdemo serve --project /path/to/project
```

Opens a local app at `http://127.0.0.1:8765` (override with `--port`).
You describe the demo in the brief box, watch screenshots stream in as
it explores, confirm the proposed intent, then review the storyboard —
editing any scene's narration inline — before approving the render.
Developer detail (phase rail, artifacts, agent log, costs) lives behind
the header's Inspector.

### CLI

In a project with a running web app:

```bash
instantdemo generate \
  --url http://localhost:3000 \
  --source ./src \
  --describe "show the signup flow"
```

The CLI walks through all six phases, opening each intermediate artifact in `$EDITOR` for review. To skip the editor checkpoints, add `--no-edit`. To resume mid-pipeline after edits, add `--from-phase N`.

Common variations:

```bash
# Run a single phase (debug / dev iteration)
instantdemo phase 3 --url ... --source ...

# Render-only from an existing demo-script.json
instantdemo render demo-script.json -o demo.mp4

# Use a different TTS voice
instantdemo render demo-script.json --tts kokoro --kokoro-voice af_bella
```

### Claude Code skill

```
/generate-demo show the Active Sessions page and click a session card
```

Or with no arguments — the skill explores the codebase and asks which flow to demo:

```
/generate-demo
```

## TTS providers

| Provider | Quality | Setup | Cost |
|---|---|---|---|
| **Pocket TTS** (default) | High, local, **clonable** | `pip install 'instantdemo[pocket-tts]'` | Free |
| **Kokoro** | High, local | `pip install "kokoro>=0.9.4" soundfile` | Free |
| **Google Cloud WaveNet** | Natural | `gcloud auth login`, set `GCP_PROJECT` in `.env` | Free tier ~1M chars/mo |
| **ElevenLabs** | Most natural | Set `ELEVENLABS_API_KEY` + `ELEVENLABS_VOICE_ID` in `.env` | Paid |
| **Piper** | Robotic, local | `pip install 'instantdemo[piper]'`, download a model file | Free |

Pocket TTS ships 26 stock voices (default `alba`) with instant preview in
the GUI, plus **voice cloning** from a short reference recording — the
cloning weights are gated, so accept the terms on the model's HuggingFace
page and authenticate first. Voice is per-project state in
`<project>/tts.json`, which also carries pronunciation respellings.

See [TTS-PROVIDERS.md](TTS-PROVIDERS.md) for setup details.

## Output layout

```
your-project/
├── intent.json              # your curated input (goal, audience, tone, focus)
├── tts.json                 # per-project voice + pronunciations
├── demo-script.json         # the version-controllable script (Phase 5 output)
├── demo.mp4                 # the rendered video (Phase 6 output)
├── demo.srt                 # captions
└── .instantdemo/            # intermediate artifacts (add to .gitignore)
    ├── storyboard.json      # THE canonical artifact phases 2-5 read and write
    ├── phase1.md … phase6.md  # per-phase views/reports
    ├── phase4-diff.md       # what the dress rehearsal changed, and why
    ├── exploration/         # Phase 1 screenshots (the live filmstrip)
    ├── rehearsal/           # Phase 4 per-scene thumbnails
    ├── takes/v<N>/          # versioned takes — every render is restorable
    ├── segment-timing.json  # per-segment time ranges in demo.mp4
    ├── state.json           # per-phase status, costs, durations
    └── metrics.jsonl        # append-only history (one row per phase per run)
```

`storyboard.json` is the canonical document the middle of the pipeline
operates on; `demo-script.json` is the deterministic projection of it that
the renderer consumes. Either is worth committing — they're the source of
truth for re-renders, and unlike a screen recording, they're diffable.

## Origin

Built as a proof of concept inside [claude-code-analytics](https://github.com/sujankapadia/claude-code-analytics), where Claude Code authored the demo pipeline end-to-end by reading frontend source code for selectors, writing narration, and wiring up TTS + Playwright + ffmpeg.

The standalone CLI was extracted to make the same workflow available without a Claude Code session — usable from CI/CD, scripts, automation, or anywhere with a Claude subscription. See [CLI-DESIGN.md](CLI-DESIGN.md) for the architectural rationale.
