# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-05-01

The first packaged release. Adds a standalone CLI alongside the existing
Claude Code skill.

### Added

- **`instantdemo` CLI**, distributed via `pip install instantdemo`. Built
  on the [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python)
  with OAuth (no API key required — uses your Claude subscription).
  Subcommands:
  - `instantdemo generate` — runs the full 5-phase workflow (analyze →
    narrate → gather → script → validate) end-to-end. Opens each
    intermediate artifact in `$EDITOR` between phases for review.
  - `instantdemo phase {1..5}` — runs a single phase, useful for dev
    iteration or resuming after manual edits.
  - `instantdemo render <demo-script.json>` — render-only, takes a
    finished script and produces the MP4. The same engine the skill
    invokes.
- **State and metrics** in `.instantdemo/`:
  - `state.json` — per-phase status, timestamps, and last-run metrics.
  - `metrics.jsonl` — append-only history with one row per phase per
    run, including token counts and cache reuse stats.
- **Optional dependencies** for TTS providers: `instantdemo[kokoro]`
  (recommended — local, free, high quality), `instantdemo[piper]`,
  and `instantdemo[all-tts]`. Google Cloud and ElevenLabs use existing
  `gcloud` / API-key auth, no extra pip deps required.
- `--no-edit` flag to skip the `$EDITOR` checkpoints when running
  non-interactively.
- `--from-phase N` flag on `generate` to resume a run after editing an
  intermediate artifact by hand.

### Changed

- **Renderer relocated.** `render.py` moved from
  `plugins/instantdemo/skills/generate-demo/scripts/render.py` to
  `src/instantdemo/render.py`. The plugin bundle no longer ships a
  `scripts/` directory.
- **Skill `SKILL.md` updated** to invoke `instantdemo render` instead
  of `python ${CLAUDE_SKILL_DIR}/scripts/render.py`. Skill prerequisites
  now collapse to a single `pip install 'instantdemo[kokoro]'` (plus
  `playwright install chromium` and `ffmpeg`) instead of the prior
  piecemeal install steps.
- **Audio concat stage** in the renderer now uses ffmpeg's
  `filter_complex concat` filter rather than the concat demuxer with
  `-c copy`. The demuxer didn't normalize input formats; mismatched
  sample rates between TTS-generated audio (Kokoro: 24000 Hz mono) and
  silence helpers (44100 Hz stereo) caused phantom expansion of the
  silence segments, which `-shortest` then truncated from the END of
  the audio stream — eating the last several seconds of narration. The
  filter approach normalizes to a common format and produces correctly-
  duration output.

### Breaking changes

- **Skill users must now `pip install 'instantdemo[kokoro]'` (or another
  TTS extra)** before the skill's render step works. The plugin bundle
  no longer carries the rendering pipeline; it depends on the
  pip-installed package. If you previously had the skill's renderer
  set up via piecemeal `pip install playwright`, `pip install kokoro`,
  etc., a single `pip install 'instantdemo[kokoro]'` replaces all of it.

### Known limitations

- Validation in Phase 5 cascades when an early selector check fails
  inside a multi-step interaction (e.g. a modal dialog). Existence of
  the upstream button is verified, but selectors *inside* the dialog
  show as WARN rather than PASS because the probe doesn't actually
  click the button.
- No progress indicator yet for the AI phases — they stream the agent's
  output as it arrives, but there's no top-of-screen status / spinner.
  Tracked in [#2](https://github.com/sujankapadia/instantdemo/issues/2).
- `--auto` flag for fully non-interactive runs (skip checkpoints
  entirely, even for review) is planned but not yet shipped. Tracked
  in [#1](https://github.com/sujankapadia/instantdemo/issues/1).
