# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when
working with code in this repository. Updated 2026-05-16 to reflect
the current 6-phase agent pipeline + GUI architecture.

For the deeper architecture reference, see `ARCHITECTURE.md`.

## What This Is

InstantDemo generates narrated demo videos of running web apps from a
URL + (optional) source code. A Claude Agent SDK pipeline reads the
codebase, plans a narrative, infers selectors, verifies them against
the live app, emits a demo script, and renders it with Playwright +
TTS + ffmpeg. Output is an MP4 + the JSON script that produced it.

Extracted from `claude-code-analytics`
(`github.com/sujankapadia/claude-code-analytics`), where the original
pipeline was built. Now a standalone project with a CLI, a local GUI,
and a Claude Code skill.

## Surfaces

InstantDemo runs in two surfaces:

1. **GUI** (primary surface) — `instantdemo serve` spawns a local
   FastAPI + React app at `http://127.0.0.1:8770` (or
   user-specified port). Cold-start the pipeline via New Project,
   watch phases stream live, inline-edit segment narration, re-render
   audio without re-rendering visuals.
2. **CLI** — `instantdemo generate` (full pipeline) and `instantdemo
   phase N` (one phase). Older surface; still maintained.

The pipeline logic is the **same in both surfaces** — orchestration
is shared (`src/instantdemo/phases/`); only the user interface
differs.

There's also a **Claude Code skill** at
`plugins/instantdemo/skills/generate-demo/` for invoking the pipeline
from another project's Claude Code session via `/generate-demo`.

## Installing dependencies

```bash
# Core + GUI
pip install -e ".[gui,dev]"
playwright install chromium
brew install ffmpeg

# TTS provider (Pocket TTS is the default since M3)
pip install -e ".[pocket-tts]"            # = pocket-tts + soundfile

# Optional alternative providers (CLI-only; no GUI surface)
pip install "kokoro>=0.9.4" soundfile     # Kokoro (local, 82M)
pip install piper-tts pathvalidate        # Piper (local, robotic)
pip install google-cloud-sdk              # Google Cloud TTS
# or set ELEVENLABS_API_KEY in .env       # ElevenLabs
```

**Voice is per-project state (M3, #59):** `<project>/tts.json`
carries provider / stock voice / cloned reference / pronunciation
respellings. The GUI's Voice & Pronunciation dialog (header gear)
edits it — 26 pocket stock voices with instant ▶ preview, "My voice"
cloning upload (consent + duration/silence validation), and
match→"sounds like" respellings with listen-check. Pronunciations
are applied to SPEECH TEXT only at synthesis (renderer +
segment-re-render); display text (storyboard/demo-script/captions)
is never mutated. Precedence: explicit CLI flags > tts.json >
defaults (pocket-tts/alba). Cloning weights are HF-gated — accept
terms at huggingface.co/kyutai/pocket-tts + HF auth. See
`docs/local-tts-models.md` for the bake-off behind this.

For the GUI's frontend:

```bash
npm --prefix frontend install
npm --prefix frontend run build
```

The build output is included in the wheel via hatch `force-include`,
so end users don't need Node.

## Running

```bash
# GUI (primary path)
instantdemo serve --project /path/to/project --port 8770

# CLI - full pipeline
instantdemo generate --url http://localhost:3000 --source /path/to/code --describe "Show the bookmarks page"

# CLI - single phase
instantdemo phase 4 --url http://localhost:3000 --source /path/to/code
```

**Note on auth**: Runs use the Claude Agent SDK, which prefers
`ANTHROPIC_API_KEY` over the user's Claude.ai subscription. The CLI
warns at startup if the key is set; unset it
(`unset ANTHROPIC_API_KEY`) to bill against the subscription instead.

## The 6-phase pipeline

Sequential phases, each reading the prior's artifact, each with a
narrow tool allowlist:

| # | Internal name | User-facing label | Purpose | Tools |
|---|---|---|---|---|
| 1 | `analyze` | Understand | **Explore-first (M1)**: drive the LIVE APP with Playwright (screenshots stream to the GUI), optionally enriched by source + a product one-pager; proposes the demo intent for user confirmation | `Bash`, `Read`, `Glob`, `Grep` |
| 2 | `narrate` | Plan | Create `storyboard.json` (scenes: title/narration/action/target_hint) from Phase 1 + `intent.json` | (none) |
| 3 | `gather` | Inspect | Enrich scenes with selectors (+fallback arrays), wait conditions, pacing — merged by stable scene id | `Read`, `Glob`, `Grep` |
| 4 | `explore` | Explore | Dress-rehearsal: walk the plan in headless Playwright, verify selectors, reground narration; findings merge back into the storyboard as revisions | `Read`, `Bash` |
| 5 | `script` | Build | **Deterministic projection** (no agent): storyboard → `demo-script.json`, validated against `actions.py` | (pure code) |
| 6 | `render` | Render | Lightweight drift check, then record video + TTS + ffmpeg merge | `Read`, `Bash` |

**The three-stage cold start (M1+M2):** the GUI cold start is THREE
runs gated by user review —
1. phases `[1]` (exploration: pre-flight screenshot on the New
   Project form, live filmstrip via `screenshot` SSE events,
   fenced-JSON payload with `intent_proposal`/`screens`/`warnings`
   recorded to state.json) → **intent-confirmation card**
   (`intent_confirmed` marker);
2. phases `[2,3,4]` (plan/inspect/rehearse; Phase 4 saves
   `s<N>.png` rehearsal thumbnails to `.instantdemo/rehearsal/`,
   streamed live) → **the storyboard gate**: StoryboardView renders
   scene cards (thumbnail, status chip, verification notices,
   inline narration editing via
   `PATCH /api/project/storyboard/scenes/{id}` — phase-0 revisions);
3. approve → phases `[5,6]` (`storyboard_approved` marker —
   truth table in `runs._storyboard_marker`; any run touching
   phase ≥5 implies approval, any 2-4 leg resets it).

Regenerate stays a single `[1..6]` run (bypasses both gates by
design). Source is OPTIONAL enrichment; an optional one-pager lives
at `product-context.md`. The filesystem jail is always on for server
runs (CLI keeps the `INSTANTDEMO_FS_JAIL` opt-in). The storyboard is
UPSTREAM-OF-RENDER truth: gate edits flow into the next render;
post-render narration fixes go through `/api/segments`. Smoke:
`scripts/smoke_phase1_explore.py` (self-contained fixture site;
`--confirm` exercises the full gate flow).

**The storyboard contract (M0):** `.instantdemo/storyboard.json` is
the canonical structured artifact phases 2–5 read and write
(`src/instantdemo/storyboard.py` — schema, per-stage validators,
projection, view renderers). Agents emit fenced JSON payloads that
runners validate (one corrective retry via
`phases.run_structured_query`) and merge; the `phaseN.md` files for
phases 2–4 are **rendered views** of the storyboard — prose edits to
them do NOT feed forward (the phase2 ANSWER block still does; edit
`storyboard.json` directly for everything else). Scene ids ("s1",
"s2", …) are runner-assigned and never reused.

**Phase 4 is the most distinctive** — it's an end-to-end dress
rehearsal with authority to revise the plan within limits (selector
swap = Level 1; narration regrounding = Level 2). Structural changes
(drop/add/reorder segments) stay BLOCKED with a humanized suggestion
that surfaces in the GUI triage panel.

See `DRESS_REHEARSAL_DESIGN.md` for the full Phase 4 design;
`prompts/phase4.md` for the prompt the agent receives.

## Code layout

```
src/instantdemo/
├── cli.py                     # CLI entry point
├── agent_client.py            # ClaudeSDKClient + PhaseDispatcher + per-phase tool allowlists
├── intent.py                  # Intent dataclass (goal/audience/tone/etc.) + load/save/synth
├── state.py                   # state.json read/write + per-phase metrics
├── render.py                  # The renderer: Playwright + TTS + ffmpeg merge
├── storyboard.py              # THE phase 2-5 contract: schema, validators, projection, views
├── actions.py                 # Closed demo-script action contract (shared with renderer)
├── prompts/                   # Per-phase prompt templates
│   ├── phase1.md ... phase4.md, phase6.md   # (no phase5 — deterministic)
├── phases/                    # Per-phase Python runners
│   ├── __init__.py            # Context, run_query_on_client, run_structured_query
│   ├── analyze.py             # Phase 1 runner
│   ├── narrate.py             # Phase 2 runner (storyboard creation + input resolution)
│   ├── gather.py              # Phase 3 runner (merge-by-scene-id enrichment)
│   ├── explore.py             # Phase 4 runner (rehearsal + convergence + findings merge)
│   ├── script.py              # Phase 5 runner (deterministic storyboard→script projection)
│   └── render.py              # Phase 6 runner (drift check + render via run_in_executor)
└── server/                    # FastAPI backend
    ├── app.py
    └── routes/
        ├── project.py
        ├── runs.py            # POST /api/runs + SSE stream
        └── segments.py        # PATCH narration + audio-only re-render + delete-segment

frontend/                      # React + Vite + shadcn UI
└── src/
    ├── components/            # Layout, Header, PhaseRail, RightPane, LogDrawer, ...
    ├── hooks/                 # useProject, useRun, useArtifact, useSegments
    └── api/                   # Typed clients for the backend routes

scripts/
├── smoke.py                   # Phase 2 smoke
├── smoke_segment_edit.py      # PATCH narration + re-render smoke
├── smoke_phase4_rehearsal.py  # Phase 4 dress-rehearsal smoke (5a/5b/5c scenarios)
└── explore/                   # Ad-hoc research scripts (e.g. Kokoro lexicon probes)
```

## Per-project state

Each project directory has:

```
<project>/
├── intent.json                # User-curated input (goal, audience, tone, focus, excludes, ...)
├── tts.json                   # Per-project voice (provider, stock/cloned voice, pronunciations)
├── demo-script.json           # Phase 5 output (consumed by Phase 6)
├── demo.mp4                   # Phase 6 output
└── .instantdemo/
    ├── state.json             # Persistent run state: per-phase status, cost, metrics
    ├── metrics.jsonl          # Append-only per-run-per-phase records
    ├── storyboard.json        # CANONICAL phase 2-5 artifact (scenes, statuses, revisions)
    ├── exploration/           # Phase 1 screenshots (GUI filmstrip)
    ├── rehearsal/             # Phase 4 per-scene thumbnails (s<N>.png, storyboard cards)
    ├── phase1.md ... phase6.md  # Phase 1/6: agent output; phases 2-4: rendered VIEWS of storyboard.json
    ├── phase4-diff.md         # Phase 4's per-segment revisions summary
    └── segment-timing.json    # Per-segment time ranges in demo.mp4
```

## Tests

There's no formal pytest suite. Three smoke scripts exercise the
pipeline end-to-end:

```bash
python scripts/smoke.py                                       # Phase 2 only, ~30s, ~$0.04
python scripts/smoke_segment_edit.py                          # PATCH + re-render, ~30s, $0
python scripts/smoke_phase4_rehearsal.py                      # Phase 4 dress-rehearsal, ~3min, ~$0.50
python scripts/smoke_phase4_rehearsal.py --scenario 5b        # deliberate selector break
python scripts/smoke_phase4_rehearsal.py --scenario 5c        # deliberate narration overclaim
```

Run these manually before tagging a release or after touching the
pipeline shape (Pydantic models, SSE event types, state.json schema,
Phase 4 prompt contract).

## Saved fixtures

Fixtures are gitignored (`fixtures/`); each subfolder is a
self-contained restoration of a prior run.

- `shakedown-active-sessions-exclude-recently-ended-2026-05-12` —
  pre-dress-rehearsal baseline against `claude-code-analytics`
- `dress-rehearsal-active-sessions-full-pipeline-2026-05-14` —
  first full-pipeline run on the new architecture
- `dress-rehearsal-claude-code-analytics-scroll-2026-05-14` —
  content-aware intent + scroll-through-conversation; the strongest
  generalizability demonstration
- `evernote-non-technical-fixed-2026-05-14` — generalizability test
  on a different stack (FastAPI + vanilla HTML)
- `source-free-evernote-jailed-2026-06-09` — first fully-isolated
  source-free run (no repo access, filesystem jail on); see
  `PRODUCT_DIRECTION.md` §5
- `source-free-cca-jailed-2026-06-09` — source-free run on the
  React app (volatile data, flaky-scroll catch); see
  `PRODUCT_DIRECTION.md` §5 Round 6
- `explore-first-evernote-2026-06-10` — first M1 two-run cold start
  (pre-flight → filmstrip → intent confirmation → demo), user-driven
  in the GUI; $0.58 total; corrected-audio demo.mp4
- `storyboard-gate-evernote-2026-06-10` — first M2 three-stage run
  (explore → confirm → live storyboard build → gate approve →
  render), user-driven; 7/7 rehearsal thumbnails; $0.70 total

To restore: `cp -r fixtures/<name>/. /tmp/restore && instantdemo
serve --project /tmp/restore --port 8770`.

## Key conventions

- **Per-phase prompts in plain files** (`src/instantdemo/prompts/phase{N}.md`).
  Editing a prompt is independent of editing the runner.
- **Session IDs are per-run, per-phase** (`phaseN-{run_id[:8]}`). The
  `run_id` is a UUID generated per pipeline invocation and threaded
  through `Context`. See issue #53.
- **PhaseDispatcher.hook strips the run-id suffix** for PHASE_TOOLS
  lookup. The dispatcher's `current_phase` carries the full session id;
  the hook does `phase_key = current_phase.split("-", 1)[0]`.
- **Agents emit fenced JSON; runners own artifacts.** Phases 2/3/4
  end their responses with one ```json block, validated with one
  corrective retry (`phases.run_structured_query`). The runner merges
  into storyboard.json and renders the phaseN.md view. Phase 4's
  findings keep their index-keyed shape in `state.json`
  (`explore_findings`) for the GUI triage panel; the runner derives
  its own `overall` from per-segment statuses (does NOT trust the
  agent's self-reported `summary.overall`).
- **Cost-delta tracking** in `PhaseDispatcher.session_cost_totals` —
  the SDK's `total_cost_usd` is cumulative for a session; we subtract
  the previous total to get per-run cost.
- **`intent.json` is the structured input**; the older
  `<!-- ANSWER -->` blocks in `phase1.md` / `phase2.md` are legacy
  CLI compat.

## Known gotchas

- **SSE pages and `networkidle`**: Playwright's `networkidle` never
  resolves on pages with Server-Sent Events. Use `domcontentloaded` +
  explicit `wait_for_selector` instead.
- **`sync_playwright` inside asyncio**: the renderer uses sync
  Playwright; in the GUI's FastAPI event loop, this must be offloaded
  via `loop.run_in_executor`. See `phases/render.py`.
- **ElevenLabs returns MP3**, not WAV. The merge phase normalizes all
  clips to WAV before concatenating.
- **Piper does not auto-download models** by name. Models must be
  downloaded manually and referenced by local path.
- **Video pacing** is controlled by `pause_after_ms` per segment. If
  the video feels too fast, increase these values.
- **Kokoro mispronounces compound names** (`instantdemo`,
  `Evernote`) and acronyms (`API`, `JSON`). A pronunciation override
  system is designed in `KOKORO_PRONUNCIATIONS.md` (issue #54) but
  not yet implemented.

## Documentation index

- `ARCHITECTURE.md` — current-state architecture reference (this is
  the doc that succeeds this file in depth)
- `ARCHITECTURE_RETHINK.md` — the question of whether to invert to an
  explore-first architecture; decision was to keep phases and add
  dress-rehearsal instead
- `DRESS_REHEARSAL_DESIGN.md` — Phase 4 dress-rehearsal design + prototype
  plan + convergence guarantees
- `KOKORO_PRONUNCIATIONS.md` — pronunciation override design (issue #54)
- `GUI-DECISIONS.md` / `GUI-IMPLEMENTATION.md` — GUI design and
  implementation notes from the M1-M3 milestones
- `CLI-DESIGN.md` — CLI subcommand structure
- `docs/` — reference material (Kokoro internals, monetization, etc.)
- `README.md` — product overview + getting started

## External dependencies (key ones)

- **Claude Agent SDK** (`claude_agent_sdk`) — long-lived
  ClaudeSDKClient + PreToolUse hooks for per-phase tool allowlists
- **Playwright** (`playwright.sync_api`) — browser automation +
  video capture
- **ffmpeg / ffprobe** — invoked via `subprocess` for audio/video
  processing
- **Kokoro** (`kokoro` pip package) — local TTS via misaki G2P +
  82M parameter model
- **FastAPI + uvicorn** — GUI backend
- **React + Vite + shadcn UI** — GUI frontend
