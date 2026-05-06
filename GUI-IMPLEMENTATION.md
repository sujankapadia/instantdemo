# GUI Implementation Plan

Milestone-based plan for building the InstantDemo GUI. Reads
`GUI-DECISIONS.md` for context on what's being built and why.

The strategy is **vertical slices** — each milestone produces
something runnable end-to-end. We avoid the trap of building all
backend then all frontend (or vice versa) and discovering integration
problems at the end.

Total scope estimate: ~12–17 working days, plus the parallel
credibility-floor track. Calendar time at side-project pace: 4–8 weeks.

---

## Pre-M0: Decisions to lock in before any code

These shape the file structure and dev workflow. Worth deciding once
rather than refactoring later.

### Module layout

GUI server lives at `src/instantdemo/server/`. Frontend source lives
at `frontend/` at the repo root:

```
instantdemo/                # repo root
├── src/instantdemo/
│   ├── cli.py              # existing — adds `serve` subcommand
│   ├── render.py           # existing
│   ├── phases/             # existing
│   └── server/
│       ├── __init__.py
│       ├── app.py          # FastAPI app
│       ├── routes/
│       │   ├── project.py  # GET /api/project, project state
│       │   ├── phases.py   # POST /api/phases/{n}/run, SSE stream
│       │   ├── segments.py # segment edit + re-render
│       │   └── settings.py # project settings (gear icon)
│       ├── streaming.py    # SSE helpers, callback plumbing
│       ├── state.py        # state.json read/write helpers
│       └── web/            # bundled frontend assets (built, gitignored)
└── frontend/               # frontend source — NOT shipped in pip pkg
    ├── package.json
    ├── vite.config.ts
    ├── tsconfig.json
    ├── tailwind.config.ts
    ├── components.json     # shadcn config
    └── src/
        ├── main.tsx
        ├── App.tsx
        ├── components/
        │   └── ui/         # shadcn components (copy-paste, owned by us)
        ├── hooks/
        └── api/
```

**Why this split:** `frontend/` lives at the repo root for clarity
(it's not "dev-only" — it's the source of truth for the UI). Built
assets land in `src/instantdemo/server/web/` and ship inside the pip
package. The build output directory is gitignored. Users never need
npm.

### Frontend dev workflow

- Run `cd frontend && npm run dev` for Vite hot reload (port 5173)
- Run `instantdemo serve` for FastAPI (port 8765 — pick something
  unlikely to clash)
- Vite proxies `/api/*` to FastAPI via vite.config.ts
- Production build: `npm run build` outputs to
  `../src/instantdemo/server/web/`. FastAPI serves those static
  assets at `/`.

### Language and frontend stack

- **TypeScript** with relaxed `tsconfig.json` (`strict: false`
  initially). Tighten as the codebase grows.
- **Tailwind CSS** for styling, set up via the official Vite plugin.
- **shadcn/ui** for accessible primitives (Dialog, Dropdown, Tabs,
  Tooltip, etc.). Components are copy-pasted into
  `frontend/src/components/ui/` via the shadcn CLI; we own and edit
  them. Built on Radix UI (behavior) + Tailwind (styling).
- **CodeMirror 6** for markdown / JSON editors (per H2).
- **Plain `useState` / `useReducer` + Context** for state in M0–M2.
  Revisit at M3 if state complexity warrants Zustand or TanStack
  Query.

shadcn setup (~30–45 minutes during Pre-M0):

```bash
npm install -D tailwindcss postcss autoprefixer @tailwindcss/vite
npx tailwindcss init -p
npx shadcn@latest init
npx shadcn@latest add button card dialog dropdown-menu tabs tooltip separator
```

After that, components are imported as
`import { Button } from "@/components/ui/button"`.

### Build & release

- `pyproject.toml` adds optional extra `[gui]`:
  ```toml
  [project.optional-dependencies]
  gui = ["fastapi>=0.110", "uvicorn>=0.27", "sse-starlette>=2.0"]
  ```
- Install with `pip install 'instantdemo[gui]'` or
  `pip install 'instantdemo[all-tts,gui]'`
- Frontend assets are pre-built in CI before publishing; users get
  them in the wheel
- Add a Makefile or `scripts/build_gui.sh` for the local dev → build
  → install loop

### Port and host

- Default port: **8765** (memorable, unlikely to clash)
- Bind to **127.0.0.1 only** (never 0.0.0.0) — privacy posture, no
  cross-network access
- `instantdemo serve --port N` to override

---

## M0 — Walking skeleton (~1–2 days)

**Goal:** prove the architecture end-to-end with the layout shell in
place. Phase rail rendered with real status from `state.json`. No
artifact viewing, no editing, no streaming yet — but the chrome is
there for M1 to fill in.

### Deliverable

Open browser to `localhost:8765`, see the IDE-style layout shell:

- Header: project name, gear icon (non-functional placeholder)
- Phase rail: 5 phase pills with status from `state.json`
  (✓ complete / ● running / ○ pending / ✗ error), cost + duration
  on hover
- Editor pane (left ~60%): empty placeholder
- Video + segments pane (right ~40%): empty placeholder
- Log drawer (bottom): collapsed placeholder

Styled with Tailwind + shadcn primitives so it looks like a real app,
not raw HTML.

### Tasks

1. Add `[gui]` optional extra to `pyproject.toml`
2. Scaffold `src/instantdemo/server/app.py` with FastAPI + one route:
   `GET /api/project` returns `state.json` contents (project name,
   phases dict with status/cost/duration per phase)
3. Scaffold `frontend/` with Vite + React + TypeScript
4. Set up Tailwind + shadcn (per Pre-M0 instructions); add base
   components: button, card, separator, tooltip
5. Vite config: dev proxy `/api/*` → `localhost:8765`
6. Build the layout shell: header, phase rail, two empty panes, log
   drawer. All using shadcn primitives + Tailwind
7. PhaseRail component fetches `/api/project` and renders 5 pills
   with real status, cost-on-hover (Tooltip from shadcn)
8. Wire `instantdemo serve` CLI subcommand → uvicorn (in-process,
   not subprocess); auto-open browser unless `--no-open` flag set
9. Static-file mount: FastAPI serves `server/web/` at `/`
10. `scripts/build_gui.sh` — runs `npm run build`, ensures output
    landed in `src/instantdemo/server/web/`

### Acceptance

- [ ] `pip install -e '.[gui]'` works
- [ ] `cd frontend && npm install && npm run dev` works
- [ ] `instantdemo serve` starts on 127.0.0.1:8765, opens browser
- [ ] Browser shows full layout shell (header + phase rail + empty
      panes + drawer) styled with Tailwind
- [ ] Phase rail reflects real `state.json` status — running this
      against `claude-code-analytics` shows all 5 phases as ✓
- [ ] Hot reload works (edit React → browser updates without
      restarting FastAPI)
- [ ] Empty project state (`.instantdemo/` missing) doesn't crash;
      shows a placeholder ("No project here yet")

---

## M1 — Read-only viewer (~2–3 days)

**Goal:** the GUI is useful as a `.instantdemo/` viewer even without
run controls. All artifacts visible, video plays.

### Deliverable

The IDE-style three-region layout from the UX sketch, populated from
existing project files. Click phase pills to switch artifacts. Video
plays. Segments listed. No editing.

### Tasks

(Layout shell is already in place from M0. M1 fills in the panes.)

1. Install CodeMirror 6 with markdown + JSON modes
2. Endpoints:
   - `GET /api/project/artifacts/{phase}` — returns artifact contents
     (markdown for 1/2/3/5, JSON for 4)
   - `GET /api/project/video` — streams the rendered MP4
   - `GET /api/project/segments` — parsed segments from script.json
3. Phase pills become clickable — selection drives editor pane
4. Editor pane: read-only CodeMirror, switches content based on
   selected phase
5. Video pane: HTML5 `<video>` with the rendered MP4
6. Segments list: each segment shows index, action, narration text,
   duration. Click → jumps video to that timestamp
7. Markdown rendering for phase artifacts (use `react-markdown` or
   render to HTML server-side)

### Acceptance

- [ ] Open `claude-code-analytics` project, see all 5 phase artifacts
      readable
- [ ] Video plays in right pane
- [ ] Click segment 7 in list → video jumps to segment 7's timestamp
- [ ] No editing yet — all CodeMirror instances are read-only
- [ ] Layout works at typical laptop resolution (1440×900) without
      scrolling

### Open question

Do segments include their video timestamps? Need to check current
state.json or compute from cumulative segment durations. If not
already tracked, add to render output.

---

## M2 — Run phases with SSE streaming (~3–4 days)

**Goal:** cold-start works end-to-end in the GUI. New project →
auto-advances through 5 phases → renders video. Live agent output
streamed to the bottom drawer.

### Deliverable

Click "New Project" → fill form (URL, source, describe, TTS) → watch
all 5 phases run with live agent output, render the video at the end.
Same project the CLI would produce, generated entirely in the GUI.

### Tasks

1. SSE plumbing: `streaming.py` exposes a callback the phase modules
   call with each text chunk. SSE endpoint pushes those to the browser.
2. Modify phase modules to accept a streaming callback (small change
   — the SDK already streams; we just need to thread the callback in).
3. Endpoints:
   - `POST /api/phases/{n}/run` — kicks off phase N, returns run_id
   - `GET /api/phases/{n}/stream?run_id=...` — SSE stream of output
   - `POST /api/project/new` — creates project from form data,
     bootstraps `.instantdemo/`, kicks off Phase 1
4. Frontend:
   - "New Project" button in header → modal form
   - Bottom drawer: agent log with live streaming, cost meter,
     phase tabs (so you can see Phase 1 output even while Phase 2 runs)
   - Phase pill status updates via SSE: pending → running → complete
   - Auto-advance default: when Phase N completes, kick off Phase N+1
   - Header toggle: "Pause between phases" — when on, requires user
     to click "Continue" between phases
5. Cancellation: "Stop" button on running phase. SSE channel closes,
   backend kills the agent run. (Test the SDK's cancel path.)

### Acceptance

- [ ] New project from scratch in the GUI produces the same output as
      the CLI
- [ ] Agent output streams live to the bottom drawer
- [ ] Phase pills update status in real time
- [ ] Auto-advance works through all 5 phases
- [ ] Pause toggle works — phases stop until user clicks Continue
- [ ] Cancel mid-phase works (SDK cancellation, log shows aborted)

### Risk

The SDK's streaming callback API and cancellation semantics need
verification. **Spike before committing to the architecture** — write
a 50-line script that calls `query()` with a callback and a cancel
token. If those don't work cleanly, we may need to fall back to
subprocess shell-out (rejected in G1, but may be forced).

---

## M3 — Iteration loop: segment editing + re-render (~4–5 days)

**Goal:** the killer feature works. Edit narration on a segment,
click "Re-render audio," see the updated video in seconds.

### Deliverable

The differentiating workflow:

1. Click segment 7 in the list → inline editor opens
2. Edit the narration text
3. Click "Re-render audio"
4. ~6 seconds later, video pane updates with new audio for segment 7

Plus: edit `instantdemo-style.md`, click "Re-run from Phase 2," watch
phases 2/3/4/5 cascade with stale indicators in between.

### Tasks

1. Inline segment editor:
   - Click segment in list → expands inline (or modal — see open
     question below)
   - Textarea for narration
   - Number input or slider for `pause_after_ms` (with current
     default + cost preview)
   - Save button (or auto-save on blur)
2. Endpoints:
   - `PATCH /api/segments/{i}` — update narration / pause_after_ms
   - `POST /api/segments/{i}/re-render-audio` — re-TTS + re-mux
   - `POST /api/segments/{i}/re-render-segment` — re-record + re-mux
3. Backend re-render logic:
   - Audio-only: regenerate this segment's WAV, re-run the audio
     concat + ffmpeg mux. Keep video clip as-is.
   - Segment re-record: replay segments 1..N-1 silently to set up
     state, record N, splice into master video.
4. Stale-state tracking:
   - State.json gains `phases.<n>.stale: bool`
   - When upstream artifact edited, mark all downstream phases stale
   - Frontend shows yellow dot on stale phase pills
   - "Re-run from here" button on each stale phase
5. Style file editor:
   - "Project style" entry in side panel
   - CodeMirror in markdown mode pointed at
     `.instantdemo/instantdemo-style.md` (created if absent)
   - Edits to this file mark Phase 2 stale (since style is layered
     into Phase 2's prompt)
6. Issue #4 (style file mechanism): build the prompt-layering logic
   in the engine. Phase modules read the style file and inject it
   into their prompts.

### Acceptance

- [ ] Edit narration on segment 7, click re-render audio, video
      updates within ~10 seconds with new audio
- [ ] Edit `pause_after_ms` (lengthen), click re-render segment,
      video updates with new pacing
- [ ] Edit `instantdemo-style.md`, see Phase 2/3/4/5 marked stale
- [ ] "Re-run from Phase 2" cascades through 2→3→4→5→render
- [ ] Cost meter accumulates correctly across cascade

### Open question

Should the segment editor expand inline (cleanest) or open as a
modal/side-panel (more screen real estate for long narration)? Inline
is the v1 default unless real estate becomes a problem.

---

## M4 — Polish (~2–3 days)

**Goal:** ship-ready quality. Edge cases handled, settings panel,
escape hatches.

### Tasks

1. Settings panel (gear icon in header):
   - Project title
   - Resolution (with `--resolution` parity)
   - TTS provider + voice choice
   - Auth state file picker (depends on #7 from credibility floor)
2. Phase 4 raw JSON editor (escape hatch):
   - When viewing Phase 4 artifact, full CodeMirror JSON editor with
     validation
   - "Save" applies edits, marks Phase 5 + render stale
3. Run history view:
   - Browse `.instantdemo/runs/<timestamp>/` directories
   - View past agent logs
   - Show diff between current state.json and a past run
4. Empty / error states:
   - Empty project (no `.instantdemo/`): show "Create a new project"
     CTA
   - Phase failed: show error, link to log, "Retry" button
   - Video missing: show placeholder + "Render" button
5. Keyboard shortcuts:
   - Cmd-S in editor → save current artifact
   - Cmd-K → switch phase
   - Cmd-Enter on segment editor → save + re-render audio
6. Error handling: SSE disconnection, partial run recovery, browser
   refresh mid-run

### Acceptance

- [ ] All settings panel fields work end-to-end
- [ ] Empty project shows helpful CTA, not a broken UI
- [ ] Failing phase doesn't crash the GUI; user sees error + retry
- [ ] Run history shows past runs with timestamps and costs
- [ ] Keyboard shortcuts work in the editor

---

## Parallel track: Credibility floor (~2 days, can run anytime)

These are engine-level features, not GUI features, but they're P0 for
the GUI being publicly demoable on real apps. Track them as separate
issues already filed.

### #6 iframe support (~1 day)

- Add `frame` field to segment schema
- Renderer dispatches via `frame_locator` when present
- Phase 3 prompt updated to emit `frame` for elements in iframes
- Phase 5 validation probes correct frame
- E2E test on a real iframe-bearing app (Stripe checkout, Storybook)

**No GUI work needed** — `frame` is invisible to the user; Phase 3
emits it, renderer uses it. JSON view in Phase 4 shows it for power
users.

### #7 auth via saved session (~1 day)

- New `instantdemo save-auth <url>` subcommand
- `--auth-state PATH` flag on `render`
- `auth_state` field in script JSON
- Documentation + security warning + .gitignore guidance

**Small GUI surface in M4 settings panel:** file picker for auth
state path.

### Sequencing

- These can land before M0 if you want to get them out of the way
- Or interleaved with GUI work (e.g., #6 between M1 and M2)
- Or parked until M4 (auth's GUI surface lives there anyway)

Recommendation: do **#7 auth before M2**, because cold-start
generation in the GUI on apps with OAuth login won't work without it.
Most "show me your dashboard" demos need this. iframe support
(#6) can wait until M4 unless you have a specific iframe-using
target app in mind.

---

## Dependencies between milestones

```
M0 walking skeleton
  └─ M1 read-only viewer
       └─ M2 run phases with streaming
            ├─ #7 auth (recommended before M2)
            └─ M3 iteration loop
                 ├─ #4 style file mechanism (engine-side, M3-internal)
                 └─ M4 polish
                      └─ #6 iframe support (recommended in M4 window)
```

Critical path: M0 → M1 → M2 → M3. Total ~10–14 days of pure GUI work.
M4 is polish; #6/#7 are engine work that fits in the gaps.

---

## What gets demoed at each milestone

Useful checkpoints for "is this worth shipping yet":

| Milestone | What you can show |
|---|---|
| M0 | Architecture works (proof to yourself, not external) |
| M1 | "Here's a viewer for your demo project" — alpha use only |
| M2 | "Generate a demo entirely in the GUI" — first usable release |
| M3 | "Edit narration, see it update instantly" — the iteration loop, **the actual product** |
| M4 | Public-ready: settings, error handling, polish |

M3 is the milestone where the product hypothesis is testable. Before
M3, the GUI is just a different UI for the CLI — useful but not
differentiating. M3 is what justifies the whole exercise.

---

## SDK spike findings

Ran three spikes against `claude-agent-sdk` 0.1.71
(`/tmp/sdk_spike.py`, `/tmp/sdk_spike2.py`, `/tmp/sdk_spike3.py` —
throwaway). Findings drove decision G3 in `GUI-DECISIONS.md`.

### Streaming + cancellation API (architecture stands)

- **`query()` returns an `AsyncIterator`** of typed messages
  (UserMessage, AssistantMessage, SystemMessage, ResultMessage,
  StreamEvent, RateLimitEvent). Async-iterate to consume.
- **Set `include_partial_messages=True`** in `ClaudeAgentOptions` to
  get per-token streaming via `StreamEvent` messages. Each carries
  `event: dict` with the raw Anthropic-API streaming payload —
  `type: content_block_delta` for token chunks.
- **Cost is on `ResultMessage.total_cost_usd`** at end of run.

### Cold-start is per-`query()` and significant

Every `query()` call launches the `claude` CLI as a subprocess and
waits ~5–10s for it to initialize. First `SystemMessage` at t=5.78s,
first `StreamEvent` at t=9.79s in our tests. A 5-phase cold-start
workflow with `query()`-per-phase pays this 5 times → ~25–50s
overhead.

### `ClaudeSDKClient` amortizes cold-start (recommended path)

The SDK also exposes `ClaudeSDKClient` — a long-lived client that
keeps one subprocess alive across many `client.query()` calls.
Spike results:

| Metric | `query()` × 5 phases | `ClaudeSDKClient` reused |
|---|---|---|
| Cold-start cost | ~30s total | ~5s once |
| Subsequent query latency | 5–10s | ~2s |
| Cancellation | `asyncio.cancel` ~6s | `client.interrupt()` instant |

`session_id` parameter gives per-phase context isolation
(no leakage between phases).

**Decision (G3 in GUI-DECISIONS.md):** migrate engine to
`ClaudeSDKClient`. Both CLI and GUI benefit. Touches all 5 phase
files but the migration is mechanical. Filed as follow-up — not
blocking M0/M1 but should land before M2.

### UX implications (still apply)

**Cold-start state.** First-run still pays ~5s for `connect()`. GUI
shows "Starting agent..." during this window — distinct from
"Loading data."

**Cancellation is instant with `interrupt()`.** UI can disable the
Stop button immediately and rely on the next `ResultMessage` to
arrive within ~1s. No "Stopping..." purgatory.

**Streaming spread depends on response length.** For tiny prompts
("count to 10"), `StreamEvent`s arrive within 0.05s. For real
Phase prompts (~30s of generation), events spread over the full
duration — what gives the GUI live-feel output.

**Cost-counting during cancellation.** With `interrupt()`, the
`ResultMessage` arrives almost immediately and carries the partial
cost. Less of a worry than with `query()`-based cancellation.

## Risk register

**SDK streaming + cancellation semantics (M2).** ✓ Resolved by
spike — see findings above. Architecture stands; UX must
accommodate cold-start and cancel-settle latencies.

**Frontend bundle size.** React + CodeMirror 6 + video preview will
be 500KB+ gzipped. Acceptable for localhost, but worth verifying it
doesn't hurt the dev experience.

**Segment re-record state setup (M3).** Replaying segments 1..N-1
silently to set up page state for re-recording N is delicate.
Failure modes: replay diverges from original (different seed data,
auth expired, race conditions). Test on the existing
claude-code-analytics demo before generalizing.

**Pre-built frontend assets in pip package.** Hatchling needs to
include `src/instantdemo/server/web/**` in the wheel. Easy to forget;
test the wheel-install path explicitly.

**Concurrent users.** v1 assumes single-user, single-machine. If two
browsers open the GUI on the same project, edits could conflict.
Acceptable for v1 (document the limitation); revisit if it bites.

---

## Out of scope for v1

Worth listing so we don't scope-creep:

- Multi-project dashboard
- Hosted version
- GitHub App / CI integration
- Demo gallery / sharing / publishing
- Authentication on the GUI itself (it's localhost-only)
- Real-time collaboration / multi-user editing
- Mobile / responsive layout
- Dark mode (or light mode — pick one and stick with it)
- Internationalization
- Plugin system
- Analytics / telemetry

All of these are real features eventually, but each is a v1.5+ or v2+
discussion.

---

## What to build first

SDK spike already complete (see findings above). Architecture stands.

Concrete starting tasks:

1. Add `[gui]` extra to `pyproject.toml` (~10 min)
2. Scaffold `src/instantdemo/server/app.py` with FastAPI and the
   `GET /api/project` route reading `state.json` (~30 min)
3. Wire `instantdemo serve` CLI subcommand → uvicorn (~15 min)
4. Scaffold `frontend/` with Vite + React + TS (~15 min)
5. Set up Tailwind + shadcn (~30–45 min)
6. Build the layout shell with placeholder panes + functional phase
   rail (~half day)

End of M0: walking skeleton renders against the existing
claude-code-analytics project.
