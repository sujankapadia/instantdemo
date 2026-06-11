# Plan: Iteration-loop UX polish — during-run minimalism + icon discoverability

## Context

Two related UX cleanups for the most common journey (the iteration
loop: watch demo → tweak → watch better demo):

**Problem 1: During a run, the GUI auto-opens too much.**
Today every run auto-shows the phase rail and the agent log drawer.
That's useful for developers / debugging — but for end users in the
iteration loop, it's noise on top of the video they're already
focused on. The current end-user experience is "hit Regenerate →
your video gets pushed aside by stacks of chrome → it returns when
the run finishes." We want: "hit Regenerate → see a compact
'Phase 4 of 6, $0.31' line in the header → video stays in place →
new video appears."

**Problem 2: Segment row edit/delete affordances are invisible.**
Today the pencil / re-render / trash icons on each segment row are
`opacity-0` and only appear on hover. New users have no idea you
can edit narration or delete a segment until they accidentally
hover. The user flagged this discoverability gap previously.

After this change:
- During runs (with the details toggle off), the page stays calm:
  video + segments + a compact "Phase N of 6 · Name · $X.XX" line
  in the header. Phase rail and log drawer don't auto-open. Power
  users still get full visibility via the details toggle.
- After a run completes, the cost stays visible in the header
  (today it disappears when status returns to idle).
- Segment row icons are faintly visible at rest (~40% opacity) and
  brighten to full on hover — so the affordances are discoverable
  without hovering.

## Approach

One commit. Three coordinated changes; partial states aren't
broken but the UX only makes sense together.

### 1. Compact run-progress indicator in the header

`frontend/src/components/Header.tsx`:

- Add a new prop `currentPhase: number | null` (sourced from
  `useRun().currentPhase`).
- During active runs (`isActive`), render a compact run-progress
  line: a spinner + `Phase N of 6 · <PhaseName>` (using
  `phaseName(N)` from `@/lib/phases`).
- Place it to the left of the existing cost pill so during a run
  you see: `[spinner] Phase 4 of 6 · Explore · $0.31`.
- Relax the cost pill's visibility:
  - Today: `showCost = runStatus !== 'idle' && (cumulativeCost > 0 || isActive)`
  - New: `showCost = cumulativeCost > 0 || isActive` — keeps the
    last run's cost visible after the run terminates. The user
    sees the cost of the demo they just watched.

`frontend/src/components/Layout.tsx`:

- Pass `currentPhase={run.currentPhase}` into the Header.

### 2. Hide phase rail + log drawer during runs (when details off)

`frontend/src/components/Layout.tsx`:

- Phase rail visibility: change `showPhaseRail = detailsVisible || isRunActive`
  to `showPhaseRail = detailsVisible`. Rail no longer auto-shows on
  run start.
- Move log-drawer auto-open logic from `LogDrawer` up to Layout.
  New useEffect in Layout watching `run.status` transitions:
  ```tsx
  useEffect(() => {
    const isRunning = run.status === 'starting' || run.status === 'running'
    if (isRunning && !wasRunningRef.current && detailsVisible) {
      setLogOpen(true)
    }
    wasRunningRef.current = isRunning
  }, [run.status, detailsVisible])
  ```
- Gated on `detailsVisible`: auto-open only fires when the user
  has explicitly opened details. End-user mode stays clean.

`frontend/src/components/LogDrawer.tsx`:

- Remove the internal auto-open useEffect (lines 43–57). Drawer
  is now fully controlled by Layout. The Esc-clean-view code we
  shipped recently already routes through `logOpen` so this is a
  natural completion.
- Keep the controlled-or-uncontrolled fallback in `setOpen` for
  any unforeseen callers — but in practice Layout always controls.

### 3. Make segment row icons always faintly visible

`frontend/src/components/SegmentsList.tsx`:

- `RowIconButton` opacity classes (around line 488):
  - Today: `'opacity-0 group-hover:opacity-100 focus-within:opacity-100'`
  - New: `'opacity-40 group-hover:opacity-100 focus-within:opacity-100'`
- One-line change. Disabled state (`opacity-30`) still overrides as
  the lower priority class via cn() — disabled icons remain dimmer
  than enabled-at-rest icons.

## Critical files to modify

- `frontend/src/components/Header.tsx` — new run-progress section + cost visibility
- `frontend/src/components/Layout.tsx` — pass currentPhase, drop isRunActive from rail gate, lift log auto-open
- `frontend/src/components/LogDrawer.tsx` — remove internal auto-open useEffect
- `frontend/src/components/SegmentsList.tsx` — RowIconButton opacity class

Existing utilities reused:
- `phaseName(n)` from `frontend/src/lib/phases.ts` for the header's phase label
- `formatCostUsd` from `frontend/src/lib/format.ts` (already used by cost pill)
- `useRun().currentPhase` and `useRun().cumulativeCost` (no hook changes)
- `Loader2` icon from `lucide-react` (already used in many places for spinners)

## Verification

Plumbing:
- `npm --prefix frontend run build` succeeds — catches missing imports / type errors

Manual (browser):
1. Cold-start full pipeline with **details toggle off**:
   - Header shows `[spinner] Phase N of 6 · Name · $X.XX`
   - Phase rail does NOT appear; log drawer does NOT auto-open
   - When run completes: cost stays visible, progress line disappears
2. Same with **details toggle on**:
   - Header shows the progress line same as above
   - Phase rail appears (as today); log drawer auto-opens (as today)
3. Esc still works: collapses details + log drawer; cost pill in
   header is unaffected (correct — it's not "chrome", it's persistent
   state)
4. Segment list at rest (no hover): edit / delete icons faintly
   visible on each row (~40% opacity)
5. Hovering a segment: icons brighten to full opacity (transition
   preserved)
6. Inline segment editor flow still works: pencil → edit → save →
   re-render audio
7. Failed phase still triggers the auto-open-on-error (#29) → details
   + phase artifact visible regardless of new gating

Cost: no agent runs needed for verification; can use the existing
`/tmp/shakedown` project state.
