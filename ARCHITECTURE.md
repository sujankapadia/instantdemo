# InstantDemo architecture

Authored 2026-05-16. Current-state reference for the InstantDemo
pipeline + GUI + renderer. For the higher-level project guidance,
see `CLAUDE.md`. For specific subsystems, see the design docs
referenced at the end.

## 1. What InstantDemo is

InstantDemo generates **narrated demo videos of running web apps**
from a URL + (optional) source code. A multi-phase Claude Agent SDK
pipeline reads the codebase, plans a narrative, finds stable CSS
selectors, verifies them against the live app, emits a demo script,
and renders the result as MP4 with TTS narration.

Two surfaces wrap the same pipeline:

- **Local GUI** — `instantdemo serve` spawns a FastAPI + React app
  at `http://127.0.0.1:8770`. Primary user interface.
- **CLI** — `instantdemo generate` / `instantdemo phase N`. Older
  surface; still maintained for headless / scripting use cases.

## 2. The 6-phase pipeline

Phases run sequentially. Each reads the prior phase's artifact and
emits its own. Each phase has its own prompt, its own tool allowlist,
and its own success contract.

```
       ┌───────────┐    ┌─────────┐    ┌──────────┐    ┌──────────┐    ┌─────────┐    ┌──────────┐
intent │           │    │         │    │          │    │          │    │         │    │          │
─────► │ 1 Analyze │ ─► │ 2 Plan  │ ─► │ 3 Gather │ ─► │ 4 Explore│ ─► │ 5 Build │ ─► │ 6 Render │
URL    │           │    │         │    │          │    │          │    │         │    │          │
src ─► └─────┬─────┘    └────┬────┘    └────┬─────┘    └────┬─────┘    └────┬────┘    └────┬─────┘
             │               │              │               │               │              │
             ▼               ▼              ▼               ▼               ▼              ▼
        phase1.md       phase2.md      phase3.md       phase4.md      demo-script    demo.mp4
       (markdown)      (markdown)     (markdown)     (JSON findings    (JSON)        + phase6.md
                                                     + markdown)                   + segment-timing.json
```

User-facing names: Understand / Plan / Inspect / Explore / Build /
Render. Internal identifiers (in code, state.json, metrics.jsonl):
`analyze` / `narrate` / `gather` / `explore` / `script` / `render`.

### Phase 1 — Understand (`analyze.py`)

**Purpose**: read the user's source code, build a map of the app's
structure that downstream phases can reason from.

**Input**: `intent.json` + the source directory.

**Output**: `phase1.md` — markdown summary of routes, components,
data flow, conventions.

**Tools**: `Read`, `Glob`, `Grep`.

**Why first**: Phase 2's narrative grounding and Phase 3's selector
inference both depend on understanding what the app *is*. Without
source analysis, downstream phases degrade to live-only inspection
which produces worse results.

### Phase 2 — Plan (`narrate.py`)

**Purpose**: write a narrative plan (markdown) describing the demo's
arc — segments, beats, narration text, target elements.

**Input**: `phase1.md` + `intent.json` (audience, tone, length, focus,
excludes, addenda).

**Output**: `phase2.md` — per-segment narrative with action,
narration, high-level target description.

**Tools**: none — pure reasoning over Phase 1's output.

**Deterministic input resolution**: the runner's `_resolve_inputs`
substitutes the user's intent values directly into the prompt header
(`Audience: non-technical (general user, not a developer)`). The agent
treats them as facts about the demo, not as defaults to reason about.
This was the lesson behind the audience-default fix (commit
`01374a8` + the prompt simplification).

### Phase 3 — Inspect (`gather.py`)

**Purpose**: find stable CSS selectors for each segment by grepping
the source code for actual attribute values (not component names).

**Input**: `phase1.md` + `phase2.md`.

**Output**: `phase3.md` — per-segment plan with a primary selector,
fallback selectors, wait conditions, and notes.

**Tools**: `Read`, `Glob`, `Grep`.

**Convention survey upfront**: the agent first counts which selector
convention the project uses (`data-testid`, `data-test`, `data-cy`,
ARIA labels, hrefs). Then uses that convention as the primary
strategy. Pre-#43 the agent would infer testids from component file
names; the prompt now requires actual attribute lookup.

### Phase 4 — Explore (`explore.py`) — the dress-rehearsal

**Purpose**: walk every segment in sequence against the **live app**
via headless Playwright, observe what actually happens, and revise
the plan within bounded authority.

**Input**: `phase3.md` + the live app URL.

**Output**: `phase4.md` — fenced JSON findings block (structured)
plus per-segment markdown body (human-readable). Plus
`phase4-diff.md` summarizing revisions made.

**Tools**: `Read`, `Bash`. (Bash is used to write + run a Playwright
rehearsal script via heredoc.)

**Authority levels** (deterministic, enforced by the prompt + runner):

| Level | Scope | Action | Outcome |
|---|---|---|---|
| L1 | Mechanical | Selector swap, timing adjust, wait condition refinement | `PASS` + `selector_swapped: true` |
| L2 | Narration regrounding | Rewrite a segment's narration to match observed state, within intent constraints | `PASS` + `narration_revised: true` |
| L3 | Structural | Drop, add, or reorder segments | `BLOCKED` + humanized suggestion |

**Why dress-rehearsal**: Phase 3's plan is a hypothesis based on
source. Phase 4 makes it a *verified plan* by exercising it against
the live app. Catches whole classes of failures the source can't
predict: SPA routing surprises, data-dependent visibility, timing
races, stale claims like "5 active sessions" when there are 3.

**Convergence guarantees** (all enforced by the runner):

- **Max iterations**: 3. The agent can re-rehearse if it can fix
  issues within authority.
- **Soft per-iteration wall-clock budget**: `max(180s, segments ×
  25s)`. Checked between iterations only (mid-iteration cancellation
  would discard all in-flight work).
- **No-progress detection**: if iteration N produces the same
  `frozenset` of FAIL signatures as N-1, stop immediately.
- **Overall ceiling**: 30 minutes, runner-side safety net.

See `DRESS_REHEARSAL_DESIGN.md` for the full design, including the
test scenarios (5a/5b/5c) that validated the architecture.

### Phase 5 — Build (`script.py`)

**Purpose**: translate Phase 4's verified plan into the strict JSON
schema (`demo-script.json`) that the renderer consumes.

**Input**: `phase4.md` (the agent reads the per-segment markdown
body, not the JSON findings).

**Output**: `demo-script.json` at the project root.

**Tools**: `Read`, `Write`.

**Runner-side structural validation** (post-write, in `script.py:79`):

```python
json.loads(artifact.read_text())                       # 1. valid JSON?
for required in ("title", "resolution", "segments"):   # 2. top-level keys?
    if required not in script: raise ...
if not isinstance(script["segments"], list) or not script["segments"]:
    raise ...                                          # 3. non-empty list?
for seg in script["segments"]:                         # 4. per-segment shape?
    for required in ("action", "narration"):
        if required not in seg: raise ...
```

A failed validation halts the pipeline. Phase 6 never sees an
invalid script.

**Why LLM-driven translation here** (rather than programmatic
parsing of Phase 4): the per-segment data lives in markdown that
varies slightly by segment type. The LLM does the field mapping
naturally; programmatic parsing would need fragile regex.

### Phase 6 — Render (`render.py` runner + `src/instantdemo/render.py`)

**Purpose**: lightweight drift check (curl + first-action smoke),
then record the video.

**Input**: `demo-script.json`.

**Output**: `demo.mp4` + `phase6.md` (drift-check report) +
`segment-timing.json` (per-segment time ranges, used by GUI for
click-to-seek).

**Tools**: `Read`, `Bash`.

**Mechanics**:

1. Agent runs a drift check (curl + a one-action Playwright probe).
   Emits `RENDER_OK` or `RENDER_BLOCKED: <reason>` (legacy text
   directive — see note below).
2. If OK, the runner calls the actual renderer via
   `loop.run_in_executor(None, ...)` to keep sync Playwright out of
   FastAPI's asyncio loop (#33).
3. Renderer launches Chromium with `record_video_dir`, runs each
   segment, generates TTS clips, ffmpeg-merges to MP4.

**Note on the text directive**: Phase 6 uses a legacy `RENDER_OK` /
`RENDER_BLOCKED` text pattern rather than structured JSON findings.
This is inconsistent with Phase 4's structured contract and is the
remaining migration target — should converge eventually.

## 3. Cross-cutting infrastructure

### Long-lived `ClaudeSDKClient` + `PhaseDispatcher`

A single `ClaudeSDKClient` is created at server startup (or CLI
invocation) and shared across all phases of all runs. The
`PhaseDispatcher` tracks `current_phase` and serves the `PreToolUse`
hook callback. See `agent_client.py:make_agent_client`.

### PreToolUse hooks for per-phase tool allowlists

Per-phase tool allowlists are enforced at the SDK layer, not at the
prompt layer:

```python
PHASE_TOOLS = {
    "phase1": frozenset({"Read", "Glob", "Grep"}),
    "phase2": frozenset(),
    "phase3": frozenset({"Read", "Glob", "Grep"}),
    "phase4": frozenset({"Read", "Bash"}),
    "phase5": frozenset({"Read", "Write"}),
    "phase6": frozenset({"Read", "Bash"}),
}
```

Every tool call the agent attempts goes through
`PhaseDispatcher.hook`, which returns `{permissionDecision: "allow"}`
or `{permissionDecision: "deny", permissionDecisionReason: "..."}`.
The agent literally cannot call a tool outside its phase's
allowlist, even if the prompt drifts.

### Session isolation per run per phase

Each pipeline run gets a fresh UUID `run_id`. Each phase derives its
session ID as `f"phase{N}-{run_id[:8]}"`. The hook strips the suffix
to look up PHASE_TOOLS:

```python
phase_key = current_phase.split("-", 1)[0]
```

**Why**: the SDK threads conversation history per `session_id`.
Pre-#53, runs reused fixed IDs (`"phase4"`), so the agent for Phase 4
saw ALL prior runs' Phase 4 queries. Caused format dropouts (agent
skipped the JSON contract because it "already gave that earlier"),
stale-prior decision leakage, silent opinion bleed. Per-run sessions
prevent the whole class.

The Anthropic prompt cache is content-keyed (not session-keyed), so
identical prompt content still caches across runs. We only lose the
conversation-prefix cache, which is what we want gone.

### Cost-delta tracking

The SDK's `ResultMessage.total_cost_usd` is **cumulative** for a
session_id. To get per-run cost we subtract the previous total
tracked in `PhaseDispatcher.session_cost_totals`. Combined with
per-run session IDs, each run's `state.json` shows accurate per-phase
cost.

### `intent.json` — structured user input

```json
{
  "goal":     "Show the Active Sessions page, ...",
  "audience": null,
  "tone":     null,
  "length":   null,
  "focus":    [],
  "excludes": ["Recently ended sessions"],
  "addenda":  []
}
```

Phase 2's `_resolve_inputs` substitutes values into the prompt
header. `null` fields fall back to defaults defined in
`narrate.py` constants (`DEFAULT_TONE`, `DEFAULT_AUDIENCE`).

### Persistent state

- **`state.json`** — current project state. Per-phase status, cost,
  duration, token counts, plus phase-specific extras
  (`explore_findings`, `explore_overall`).
- **`metrics.jsonl`** — append-only per-run-per-phase records. One
  JSON line per phase execution; never overwritten. Useful for cost
  analytics + smoke-test assertions.

### SSE event stream

`POST /api/runs` returns a run ID. `GET /api/runs/{id}/stream`
streams Server-Sent Events:

- `run_started`, `run_complete`, `run_error`, `run_canceled`
- `phase_started`, `phase_complete`, `phase_error`
- `text_chunk` (streaming agent text deltas)
- `tool_use` (which tool the agent called, with input)

The GUI's state machine consumes these. Smoke tests assert on event
sequences.

## 4. The three concentric layers of deterministic gating

This is the architectural pattern worth naming. Structured outputs
in InstantDemo aren't a single mechanism — they're a stack of
deterministic contracts at different scopes:

```
┌──────────────────────────────────────────────────────────────────────┐
│                  Run / system layer                                  │
│  RunRequest Pydantic validation, state.json current_run_id,          │
│  SSE event types  ───── gates: can a run start? what UI to show?     │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │             Phase / between-phase layer                        │  │
│  │  Phase 4 fenced JSON findings, Phase 5 JSON validation,        │  │
│  │  Phase 6 RENDER_OK directive, state.json phase status          │  │
│  │  ──── gates: does the next phase run?                          │  │
│  │                                                                │  │
│  │  ┌──────────────────────────────────────────────────────────┐  │  │
│  │  │              Tool-call layer                             │  │  │
│  │  │  PreToolUse hook decisions                               │  │  │
│  │  │  ─── gates: each individual tool invocation              │  │  │
│  │  └──────────────────────────────────────────────────────────┘  │  │
│  └────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

Each layer constrains a different scope. **Determinism in agent
systems isn't about distrusting LLMs — it's about scoping LLM
judgment to specific decisions and surrounding those decisions with
mechanical gates.**

## 5. The GUI

### Backend (`src/instantdemo/server/`)

FastAPI app with routes under `/api/`:

- `project.py` — GET/POST project state, GET artifacts, GET phase
  details
- `runs.py` — POST `/api/runs` to start a run; SSE stream at
  `/api/runs/{id}/stream`; cancel/resume endpoints
- `segments.py` — PATCH segment narration; POST audio-only
  re-render; DELETE segment

The backend owns the long-lived `ClaudeSDKClient` and the
`PhaseDispatcher`. Run requests construct a `Context` per
invocation, threading `run_id` through to the phase runners.

### Frontend (`frontend/src/`)

React + Vite + shadcn UI. Built once via
`npm --prefix frontend run build`, output included in the wheel via
hatch `force-include`.

Key components:

- **Layout** — owns project state + run state + UI mode (details
  visible / log drawer open / phase rail shown).
- **Header** — project name, run progress indicator, cost pill,
  Regenerate / New Project buttons.
- **PhaseRail** — vertical list of phases with per-phase status
  pips, click-to-view artifact.
- **RightPane** — video player + segments list (the primary user
  surface).
- **LogDrawer** — collapsible agent log streaming SSE events.
- **EditorPane** — opened on phase artifact click; shows the
  markdown / JSON output.
- **Phase4TriagePanel** — humanized failure surface when Phase 4
  reports BLOCKED. Lists segments + the user-facing `suggestion`
  field, NOT the technical `reason`.
- **IntentEditor** — reusable form for goal/audience/tone/etc.
  Goal always visible, advanced fields behind a collapsible.
- **NewProjectForm** — initial project setup (URL + source +
  intent).

Key user flows:

- **Cold start** — New Project → fill goal + source + URL → click
  Generate Demo → watch all 6 phases stream → demo.mp4 plays
- **Regenerate** — single button on completed projects; re-runs all
  phases with the existing intent (or with the IntentEditor surface
  for editing first)
- **Segment edit** — inline-edit narration → Save → audio-only
  re-render (`-c:v copy`) preserves video; updates demo.mp4 with
  new voice over frozen frames

## 6. The renderer (`src/instantdemo/render.py`)

Three sequential stages, plus the upcoming pronunciation override
layer:

1. **TTS generation** — per-segment narration → WAV clips. Kokoro
   is the default (local, free, fast); ElevenLabs / Google / Piper
   alternatives also supported.
2. **Browser recording** — Playwright launches Chromium with
   `record_video_dir=...`, runs each segment's action, sleeps for
   `max(audio_duration, pause_after_ms)` to stay in sync.
3. **Merge** — ffmpeg concatenates audio clips with silence gaps,
   then muxes audio + video into the final MP4.

The pronunciation override layer (designed in
`KOKORO_PRONUNCIATIONS.md`, tracked as #54) will sit between TTS
and the rest — mutates `pipeline.g2p.lexicon.golds` with
user-curated entries + auto-resolved compound splits before
synthesis.

## 7. What's deliberately NOT in the architecture

- **Multi-agent peer-to-peer orchestration** (CrewAI style). One
  agent in distinct roles, not many agents communicating.
- **LLM-driven workflow / dynamic phase selection.** The phase
  sequence is fixed; the orchestrator decides what runs and when.
  Agents don't decide the outer loop.
- **Agent-judged success.** Phase 4's `summary.overall` is
  informational; the runner derives its own `overall` from
  segment statuses. The LLM doesn't gate the pipeline; the runner
  does.
- **Inline IPA tags or misaki constructor args** for pronunciation.
  Direct dict mutation on `pipeline.g2p.lexicon.golds` is the
  mechanism.
- **Agent-driven pronunciation detection.** The Kokoro miss
  detection algorithm is deterministic (cmudict + base-form
  filtering + all-caps acronym bypass); LLM-generated phonetics
  rejected as unreliable.

## 8. Lessons-as-issues (architectural war stories)

These are the issues we hit that taught us specific architectural
lessons. Listed here because they're useful reference for
understanding why the architecture is shaped this way:

- **#48 — Phase 4 structured findings + strict policy.** The
  failure mode of `EXPLORE_PARTIAL` "soldiering on with known
  issues" → broken videos shipped. Replace LLM judgment with
  deterministic gating.
- **#53 — Session memory contaminates pipeline runs.** Fixed-string
  session IDs caused format dropouts, stale-prior decision leakage,
  silent opinion bleed across pipeline runs. Thread `run_id` into
  session IDs.
- **#49 / #5 / #54 — Narration grounding vs. style vs.
  pronunciation.** Three independent concerns that initially looked
  like one. Each needs its own mechanism: prompt anti-patterns for
  style (#5), source-grounded constraints for accuracy (#49), and
  deterministic lexicon mutation for pronunciation (#54).
- **Audience-default fix.** Phase 2's prompt and the runner's
  default were independently wrong. Deterministic templating beats
  prompt-level instruction; both layers needed to be touched.

## 9. References

- `ARCHITECTURE_RETHINK.md` — the explore-first inversion considered
  and deferred; why the dress-rehearsal compromise won
- `DRESS_REHEARSAL_DESIGN.md` — Phase 4 full design + prototype plan
  + convergence guarantees
- `KOKORO_PRONUNCIATIONS.md` — pronunciation override design (#54)
- `GUI-DECISIONS.md` / `GUI-IMPLEMENTATION.md` — GUI design from the
  M1-M3 milestones
- `CLI-DESIGN.md` — CLI subcommand structure
- `CLAUDE.md` — project guidance for AI assistants (the entry point;
  this doc is the depth)
- `README.md` — product overview + getting started
- `docs/` — reference material (Kokoro internals, monetization,
  manifest design, TTS providers)

---

## Addendum (M0, 2026-06-10): storyboard.json supersedes markdown contracts

The cross-phase markdown conventions described above (segment
headings, labeled rows, prompt-embedded artifacts) were replaced by
a structured contract: `.instantdemo/storyboard.json`
(`src/instantdemo/storyboard.py`). Phases 2-4 emit fenced JSON
payloads that runners validate (one corrective retry) and merge by
stable scene id; phases 2-4's `phaseN.md` artifacts are now rendered
views of that document. Phase 5 no longer runs an agent at all — it
is a deterministic projection storyboard → demo-script.json,
validated against the closed action contract (`actions.py`).
demo-script.json, the renderer, the GUI segment endpoints, and the
Phase 4 findings shape in state.json are unchanged. See CLAUDE.md
("The storyboard contract") and PRODUCT_PLAN.md (M0) for details.
