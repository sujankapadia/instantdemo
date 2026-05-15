# InstantDemo

Generate narrated demo videos of web applications, automatically. Describe what to show; InstantDemo analyzes your codebase, writes a demo script, and renders an MP4 — no screen recording, no voiceover sessions, no video editing.

Two ways to use it:

- **CLI** — `instantdemo generate ...` from any terminal. Self-contained.
- **Claude Code skill** — `/generate-demo` from inside a Claude Code session. Conversational, with checkpoints between each step.

Both share the same engine (the `instantdemo` Python package) and produce the same JSON script format.

## How it works

The pipeline runs five phases:

```
1. analyze   → reads README, routes, components, seed data, auth
2. narrate   → picks a flow, drafts narration, segments it for pacing
3. gather    → finds stable selectors, wait conditions, action types
4. script    → writes demo-script.json (Playwright actions + narration)
5. validate  → checks URLs and selectors against the live app, then renders
                  Kokoro / Google / ElevenLabs / Piper TTS → audio clips
                  Playwright (Chromium) → browser recording
                  ffmpeg → final MP4
```

Between phases, intermediate artifacts land in `.instantdemo/`. The CLI opens them in `$EDITOR` so you can tweak the narrative or selectors before the next phase runs. Resume mid-pipeline with `--from-phase N` after edits — earlier phases re-use their existing artifacts.

Demo videos are **regeneratable**. UI changed? Edit `demo-script.json` and re-run `instantdemo render`. New feature? Add a segment. It's version-controlled JSON, not a frozen screen recording.

## Install

### CLI (primary)

```bash
pip install 'instantdemo[kokoro]'
playwright install chromium
brew install ffmpeg              # or your platform's equivalent
```

The `[kokoro]` extra bundles a free, local, high-quality TTS. To swap TTS providers later, see [TTS providers](#tts-providers) below.

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

### CLI

In a project with a running web app:

```bash
instantdemo generate \
  --url http://localhost:3000 \
  --source ./src \
  --describe "show the signup flow"
```

The CLI walks through 5 phases, opening each intermediate artifact in `$EDITOR` for review. To skip the editor checkpoints, add `--no-edit`. To resume mid-pipeline after edits, add `--from-phase N`.

Common variations:

```bash
# Run a single phase (debug / dev iteration)
instantdemo phase 3 --url ... --source ...

# Render-only from an existing demo-script.json
instantdemo render demo-script.json --tts kokoro -o demo.mp4

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
| **Kokoro** (default) | High, local | `pip install 'instantdemo[kokoro]'` | Free |
| **Google Cloud WaveNet** | Natural | `gcloud auth login`, set `GCP_PROJECT` in `.env` | Free tier ~1M chars/mo |
| **ElevenLabs** | Most natural | Set `ELEVENLABS_API_KEY` + `ELEVENLABS_VOICE_ID` in `.env` | Paid |
| **Piper** | Robotic, local | `pip install 'instantdemo[piper]'`, download a model file | Free |

See [TTS-PROVIDERS.md](TTS-PROVIDERS.md) for setup details. See [docs/kokoro-tts.md](docs/kokoro-tts.md) for Kokoro voice options.

## Output layout

```
your-project/
├── demo-script.json         # the version-controllable script (Phase 4 output)
├── demo.mp4                 # the rendered video (Phase 5 output)
└── .instantdemo/            # intermediate artifacts (add to .gitignore)
    ├── phase1.md            # codebase analysis
    ├── phase2.md            # narrative plan
    ├── phase3.md            # technical details (selectors, waits, pacing)
    ├── phase5.md            # validation report
    ├── state.json           # per-phase status, costs, durations
    └── metrics.jsonl        # append-only history (one row per phase per run)
```

`demo-script.json` is the only artifact you'd typically commit — it's the source of truth for re-renders.

## Origin

Built as a proof of concept inside [claude-code-analytics](https://github.com/sujankapadia/claude-code-analytics), where Claude Code authored the demo pipeline end-to-end by reading frontend source code for selectors, writing narration, and wiring up TTS + Playwright + ffmpeg.

The standalone CLI was extracted to make the same workflow available without a Claude Code session — usable from CI/CD, scripts, automation, or anywhere with a Claude subscription. See [CLI-DESIGN.md](CLI-DESIGN.md) for the architectural rationale.
