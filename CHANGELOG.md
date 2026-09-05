# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] — 2026-09-05

Everything since 0.1.0. The project changed shape substantially: it grew a
GUI, a sixth phase, and a canonical storyboard document.

### Added

- **Local GUI** (`instantdemo serve`, 2026-05-14) — FastAPI + React app on
  `http://127.0.0.1:8765`, now the primary surface. Watch exploration
  stream in, confirm intent, review the storyboard, edit narration inline.
  Developer detail (phase rail, artifacts, agent log, costs) sits behind
  the Inspector.
- **Phase 4 — the dress rehearsal** (`explore`, 2026-05-14). The pipeline
  went from five phases to **six**. Before recording, it walks every
  segment against the live app, verifies each selector resolves, and
  self-corrects within bounded authority: selector swaps (Level 1) and
  narration regrounding (Level 2). Structural changes stay blocked and
  surface as suggestions.
- **`storyboard.json`** (M0) — the canonical artifact phases 2–5 read and
  write. The `phaseN.md` files became rendered *views* of it.
- **Explore-first Phase 1** (M1) — Phase 1 now drives the **live app**
  with Playwright and proposes a demo intent for confirmation, rather
  than reading the codebase. Source became optional enrichment; the
  running app is the ground truth.
- **Storyboard approval gate** (M2) — scene cards with rehearsal
  thumbnails, verification notices, and inline narration editing.
- **Pocket TTS** (M3) — now the default provider: local, CPU, 26 stock
  voices, plus voice cloning. Per-project voice config in `tts.json`
  with pronunciation respellings.
- **Versioned takes** (M4) — every render is restorable history.
- **Chapters** (M5a) and **scoped chapter revision** (M5b) — revise one
  chapter and splice it into the existing film without re-recording.
- **Captions** (M6) — `demo.srt`, regenerated at every timing write.
- **Chaptered cold start** (M7) — the chapter is the unit of agent work
  in phases 2, 3 and 4; cost becomes linear in film length.
- **Filesystem jail** for agent file access, always on for server runs.
- **Closed action contract** (`actions.py`), validated at build and
  render time.
- **CI dependency CVE gate** (npm audit + pip-audit) and Dependabot.

### Changed

- **Phase numbering**: `1 analyze → 2 narrate → 3 gather → 4 explore →
  5 script → 6 render`. Phase 5 became a *deterministic projection* of
  the storyboard (no agent); the old phase-5 "validate" role is now
  phase 6's lightweight drift check before recording.
- **Default TTS** is Pocket TTS (was Kokoro). The `--tts` flag now
  overrides the project's `tts.json`, which itself falls back to
  pocket-tts.
- `instantdemo phase` accepts **1..6**.

### Fixed

- All Dependabot vulnerabilities (44: 17 high, 23 moderate, 4 low).
- `.env` was not gitignored on `main` — API keys were unprotected.
- Documentation drift: README described a five-phase, GUI-less pipeline;
  the GUI port was wrong in three docs; CLI help contradicted itself.

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
