# M2: Storyboard UI + Gate

## Context

Third PRODUCT_PLAN.md milestone — the product's center of gravity.
The storyboard (M0's canonical artifact) becomes the primary surface:
scenes as cards with rehearsal screenshots, statuses, verification
notices, and inline narration editing, gated by "Approve → render".
Cold start becomes THREE stages: [1] explore → intent confirm →
[2,3,4] plan/inspect/rehearse → STORYBOARD REVIEW → approve → [5,6]
render (Phase 5 is free/instant since M0, so the natural pause is
post-rehearsal; render spend only on approved content). Branch:
`feature/storyboard-ui`.

Settled (user-confirmed): full gate; per-scene rehearsal screenshots
in Phase 4 (M1's validated-screenshots pattern); inline NARRATION
editing at the gate (no add/remove/reorder — M4+). Regenerate stays a
single [1..6] run (documented). Power mode (detailsVisible) stays
visually unchanged.

## Part 1 — Phase 4 rehearsal screenshots

- Naming **by segment index**: `s<N>.png` in `.instantdemo/rehearsal/`
  (findings are index-keyed; no schema change). Cleared at phase start.
- `analyze.py`: parametrize the watcher for reuse —
  `watch_screenshots(dir, emit, seen, *, phase, url_prefix)` +
  `screenshot_event(name, *, phase, url_prefix)`; phase-1 call sites
  pass phase=1 + /api/project/exploration.
- `explore.py`: rehearsal_dir helper; prompt token
  `{rehearsal_dir}` via str.replace; watcher task (phase=4,
  /api/project/rehearsal) with cancel + final-scan in finally; new
  pure `link_rehearsal_screenshots(doc, dir)` — sets scene
  `rehearsal_screenshot` when `s{index}.png` exists, POPS it when not
  (stale guard) — called after merge, BEFORE save/BLOCKED-raise (gate
  gets shots even on BLOCKED); post-loop `_ensure_screenshots`: if
  zero shots while ≥1 PASS/WARN segment, ONE corrective turn in-session
  ("re-run a minimal pass saving s<N>.png per passing segment"),
  re-scan, then warn-and-continue (thumbnails are presentation, not
  correctness — never fail the phase).
- `prompts/phase4.md`: screenshot requirement in the workflow ("save
  page.screenshot s<N>.png after each segment settles; final passing
  rehearsal overwrites — correct") + worked example.
- `project.py`: `GET /api/project/rehearsal/{filename}` — exact
  mirror of the exploration file endpoint (regex whitelist +
  containment). No listing endpoint (the doc carries the refs).
- `useRun.ts` nit: dedupe screenshots by `url` not `file`.

## Part 2 — Storyboard API (new `server/routes/storyboard.py`)

- `GET /api/project/storyboard` → `{exists, storyboard: raw doc|null}`
  (exists=False not 404; raw pass-through + hand-maintained TS types).
- `PATCH /api/project/storyboard/scenes/{scene_id}` body
  `{narration}`: 409 when a run is active (run_manager.active guard,
  segments.py precedent); 404 no doc / unknown id; no-op
  short-circuit; append revision `{type:"narration", from, to,
  reason:"user edit at storyboard gate", iteration:0, phase:0}`;
  `storyboard.save`; re-render phase4.md via
  `render_phase4_view(doc, explore_findings-from-state)`; allowed
  post-render (upstream-of-render truth; takes effect on next [5,6];
  post-render edits flow through /api/segments — code comment +
  CLAUDE.md note). Register router in app.py.

## Part 3 — Gate marker

`runs.py` pure helper `_storyboard_marker(phases) -> bool | None`
applied in start_run next to intent_confirmed:
- any p >= 5 → True (approve / re-render / Regenerate)
- elif any p in (2,3,4) → False (unreviewed rehearsal leg)
- else ([1]-only) → None (untouched)
Truth table: [1]→None, [2,3,4]→False, [4]→False, [5,6]→True,
[1..6]→True, [6]→True. `ProjectState.storyboard_approved: bool=False`.

Gate visibility (frontend, derived from /api/project — reload-safe,
the IntentConfirmCard pattern): no active run AND storyboard exists
AND (phases.4 completed OR (errored AND explore_overall==BLOCKED))
AND !storyboard_approved AND phases.6 not completed (keeps legacy
projects from re-presenting an approve CTA over a finished video).

BLOCKED at the gate: failed cards carry suggestion-first notices
(Phase4TriagePanel's rule); approve disabled; bar shows "Rehearsal
found N issues" + Regenerate. Phase4TriagePanel kept but gated to
power mode only.

## Part 4 — Frontend

- `Layout.tsx`: handleIntentConfirm → phases [2,3,4]; new
  handleApprove → startRun([5,6], url, tts) (no intent body);
  end-user mode main pane: storyboard exists && phase 6 not
  completed → StoryboardView flex-[3] + RightPane flex-[2] (filmstrip
  keeps streaming rehearsal shots during [2,3,4]); after render →
  current behavior (video+segments; storyboard tab is M4). Power mode
  untouched. Skeleton/"Planning your demo…" while [2,3,4] runs with
  no scenes yet.
- `useRun.ts`: new `onPhaseComplete?(phase)` option (ref pattern like
  onComplete) → Layout refetches storyboard after each of phases
  2/3/4 — live view: scenes appear (planned) → selectors
  (hypothesized) → verification + thumbnails (verified).
- New `api/storyboard.ts`: StoryboardScene/Doc/Response types +
  fetchStoryboard + patchSceneNarration.
- New `hooks/useStoryboard.ts`: useSegments clone (generation-counter
  refetch).
- New `components/NarrationEditor.tsx`: verbatim extraction of
  SegmentEditor from SegmentsList (which then imports it).
- New `components/StoryboardView.tsx`: vertical Card list. Card:
  header (mono index, title, action badge span, status chip —
  verified emerald / warn amber / failed red / draft neutral, tooltip
  = verification.reason); body grid (rehearsal thumbnail h-24 via
  /api/project/rehearsal/<f>, ImageOff placeholder; narration with
  pencil → inline NarrationEditor → PATCH → refetch; one editor at a
  time; disabled during runs); failure/warn callout
  (suggestion-first); revisions indicator ("N revision(s)" + tooltip
  listing from→to). Sticky approve bar: "8 scenes · 7 verified · 1
  warning", "Looks good — render the video" (disabled when any scene
  failed — Phase 5 would raise anyway — or while running), BLOCKED
  adds Regenerate.

## Tests & smokes (spec-first hook: spec files before test files)

- `tests/test_phase4_screenshots.py` + spec:
  link_rehearsal_screenshots (link/pop-stale/names), watcher diff
  reuse, `_storyboard_marker` truth table.
- `tests/test_storyboard_routes.py` + spec: TestClient w/
  INSTANTDEMO_PROJECT_DIR tmp project — GET shapes; PATCH happy path
  (revision appended phase:0, updated_at bumped, phase4.md
  re-rendered when findings present); 404s; no-op;
  /api/project storyboard_approved default.
- `smoke_phase4_rehearsal.py` 5a extension: ≥1 s*.png; verified
  scenes' rehearsal_screenshot refs exist (warn on partial); ≥1
  phase-4 screenshot SSE event.
- `smoke_phase1_explore.py` `--gate` leg (supersedes --confirm):
  [2,3,4] run → storyboard exists, scenes verified|warn,
  approved==false, rehearsal PNG served; PATCH narration → revision
  on disk + view re-rendered; POST [5,6] → poll approved==true then
  CANCEL the run (marker verified without paying for a render).
  ~$0.5-0.8.

## Sequencing (gate after each)

a. Phase 4 screenshots backend (analyze watcher params, explore.py,
   phase4 prompt, rehearsal endpoint, unit tests) → pytest +
   rehearsal smoke 5a w/ new asserts (cca on :8000).
b. Storyboard GET/PATCH + tests → pytest + curl vs restored fixture.
c. Gate markers (runs.py + ProjectState + truth-table tests) →
   pytest; [4]-run shows approved=false via /api/project.
d. Read-only StoryboardView (api/hooks/component + Layout rules +
   onPhaseComplete + url-dedupe) → npm build; fixture serve: cards/
   thumbnails/chips render; power mode unchanged.
e. Editing + approve + BLOCKED UX (NarrationEditor extraction,
   approve bar, [2,3,4] confirm change, triage panel power-gated) →
   build; fixture: edit→revision+view re-render; hand-marked failed
   scene disables approve.
f. --gate smoke + docs (CLAUDE.md three-stage flow + marker +
   Regenerate note; PRODUCT_PLAN M2 tick) + npm production build →
   smokes green; L5: user drives explore → confirm → review (edits a
   narration) → approve → video on a real app; PR.

## Risks

- Agent skips rehearsal shots → M1 pattern + warn-don't-fail +
  placeholder thumbnails.
- Post-approve edits diverge from demo-script → documented
  upstream-truth rule; M4 reconciles.
- Power-mode regression → all changes inside detailsVisible===false
  branch + additive props.
- BLOCKED dead-end → suggestion cards + disabled approve + Regenerate
  CTA.
- Concurrent writes → PATCH 409 on active runs; rehearsal dir cleared
  per run.
