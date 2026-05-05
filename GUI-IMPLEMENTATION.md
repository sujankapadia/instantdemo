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

GUI server lives at `src/instantdemo/server/`:

```
src/instantdemo/
├── cli.py                  # existing — adds `serve` subcommand
├── render.py               # existing
├── phases/                 # existing
├── server/
│   ├── __init__.py
│   ├── app.py              # FastAPI app
│   ├── routes/
│   │   ├── project.py      # GET /api/project, project state
│   │   ├── phases.py       # POST /api/phases/{n}/run, SSE stream
│   │   ├── segments.py     # segment edit + re-render
│   │   └── settings.py     # project settings (gear icon)
│   ├── streaming.py        # SSE helpers, callback plumbing
│   ├── state.py            # state.json read/write helpers
│   └── web/                # bundled frontend assets (built)
└── server_dev/             # frontend source — NOT shipped in pip pkg
    ├── package.json
    ├── vite.config.ts
    ├── tsconfig.json
    └── src/
        ├── main.tsx
        ├── App.tsx
        ├── components/
        ├── hooks/
        └── api/
```

**Why this split:** the frontend source (`server_dev/`) lives in the
repo but is excluded from the pip package via the hatchling
`[tool.hatch.build]` `exclude` config. Built assets land in
`src/instantdemo/server/web/` and ship with the package. Users never
need npm.

### Frontend dev workflow

- Run `cd server_dev && npm run dev` for Vite hot reload (port 5173)
- Run `instantdemo serve` for FastAPI (port 8765 — pick something
  unlikely to clash)
- Vite proxies `/api/*` to FastAPI via vite.config.ts
- Production build: `npm run build` outputs to
  `../src/instantdemo/server/web/`. FastAPI serves those static
  assets at `/`.

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

**Goal:** prove the architecture with the smallest possible end-to-end
slice. One API endpoint, one React component, both running.

### Deliverable

Open browser to `localhost:8765`, see:

```
Project: claude-code-analytics
Phases: [✓ Analyze] [✓ Narrate] [✓ Gather] [✓ Script] [✓ Validate]
```

No styling, no editing, no streaming. Just proof that the FastAPI
server can read state.json and the React frontend can render it.

### Tasks

1. Add `[gui]` optional extra to `pyproject.toml`
2. Scaffold `src/instantdemo/server/app.py` with FastAPI + one route:
   `GET /api/project` returns `state.json` contents
3. Scaffold `server_dev/` with Vite + React + TypeScript
4. Vite config: dev proxy `/api/*` → `localhost:8765`
5. One React component fetches `/api/project` and renders phase pills
6. Wire `instantdemo serve` CLI subcommand → uvicorn
7. Static-file mount: FastAPI serves `server/web/` at `/`
8. `scripts/build_gui.sh` — runs `npm run build` and copies output

### Acceptance

- [ ] `pip install -e '.[gui]'` works
- [ ] `cd server_dev && npm install && npm run dev` works
- [ ] `instantdemo serve` starts on 127.0.0.1:8765
- [ ] Browser shows project name + phase status from a real
      `.instantdemo/` directory
- [ ] Hot reload works (edit React → browser updates without
      restarting FastAPI)

---

## M1 — Read-only viewer (~2–3 days)

**Goal:** the GUI is useful as a `.instantdemo/` viewer even without
run controls. All artifacts visible, video plays.

### Deliverable

The IDE-style three-region layout from the UX sketch, populated from
existing project files. Click phase pills to switch artifacts. Video
plays. Segments listed. No editing.

### Tasks

1. Layout shell: phase rail (top), editor (left ~60%), video+segments
   (right ~40%), log drawer (bottom, collapsed by default)
2. Install CodeMirror 6 with markdown + JSON modes
3. Endpoints:
   - `GET /api/project/artifacts/{phase}` — returns artifact contents
     (markdown for 1/2/3/5, JSON for 4)
   - `GET /api/project/video` — streams the rendered MP4
   - `GET /api/project/segments` — parsed segments from script.json
4. Phase pills: clickable, show status from state.json, show cost +
   duration on hover
5. Editor pane: read-only CodeMirror, switches content based on
   selected phase
6. Video pane: HTML5 `<video>` with the rendered MP4
7. Segments list: each segment shows index, action, narration text,
   duration. Click → jumps video to that timestamp
8. Markdown rendering for phase artifacts (use `react-markdown` or
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

## Risk register

**SDK streaming + cancellation semantics (M2).** If the
claude-agent-sdk doesn't expose clean callbacks for streaming output
or cancel tokens for in-flight runs, M2 architecture has to change.
Spike this in M0 before committing.

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

Concretely: M0 task 1 — add `[gui]` extra to pyproject.toml and
scaffold the FastAPI app. ~30 minutes. Once that runs, scaffold the
React app. By end of day 1 of M0, you should have the walking
skeleton working.

Before writing any code: spike the SDK streaming/cancellation question
(M2 risk above). 30 minutes. If the SDK doesn't support what we need,
adjust the plan before investing in the architecture.
