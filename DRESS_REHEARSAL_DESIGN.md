# Dress-rehearsal Phase 4: design and prototype plan

Authored 2026-05-13. Synthesizes the architecture-rethink discussion
in `ARCHITECTURE_RETHINK.md` into a concrete, incremental change.

## TL;DR

Upgrade Phase 4 from "page-by-page probe" to a **full end-to-end
headless dress rehearsal** that walks every segment in sequence,
captures behavioral observations between segments, and gains
authority to reground narration based on what was actually
observed. Recording in Phase 6 then replays a known-good script.

Most of the change is additive on top of Phase 4's existing
probe-script-via-Bash mechanism. No new tools, no MCP server, no
architectural inversion. The biggest substantive shift is giving
Phase 4 the authority to revise *narration* (not just selectors)
when observations contradict predictions.

---

## What Phase 4 does today (accurate baseline)

Phase 4 already does meaningful live verification:

- Writes Python probe scripts via Bash + heredoc using
  `sync_playwright`
- Groups segments by page, runs one probe per page (not per
  segment)
- Uses `wait_for_selector` with 10s timeout (handles SPA
  loading correctly)
- **Narrative alignment** — verifies that the resolved element
  matches what the narrative describes, refining selectors with
  `:has-text()` / `:has()` when content-grounding is needed
- Applies Phase 3's listed fallbacks when the primary fails
- Distinguishes FAIL_SELECTOR vs FAIL_NARRATIVE
- Emits structured JSON findings (PASS / FAIL_SELECTOR /
  FAIL_NARRATIVE / WARN) with humanized suggestions for the
  GUI triage panel
- Strict policy: any FAIL → BLOCKED (the runner halts; user
  must address)

## What Phase 4 doesn't do (the dress-rehearsal delta)

1. **Doesn't walk segments in sequence end-to-end.** Each page
   is probed independently. Phase 4 verifies "selector X exists
   on page Y" but not "click X transitions to page Z as expected,
   and then segment N+1's selector resolves on Z."

2. **Doesn't observe behavioral side effects.** Modal opened
   correctly. Hover changed the layout. Click triggered a
   redirect. None of this is visible from page-by-page spot
   probes.

3. **Doesn't observe inter-segment timing.** Animation finishes
   800ms after click but the next segment's `pause_after_ms` is
   400ms — Phase 6 would race and miss.

4. **Can't reground narration.** Phase 4 can FAIL or PASS but
   can't say "I observed only 3 active cards, not 5 like the
   narration implies — here's the revised narration." That
   capability doesn't exist today.

5. **Probe scripts are throwaway and unrelated to the
   recording.** The trace Phase 6 records is independent of
   what Phase 4 probed.

---

## Design

### Phase mapping changes

| Phase | Before | After |
|---|---|---|
| 1 Understand | Read codebase | Unchanged |
| 2 Plan | Write narrative | Writes narrative as *hypothesis*. Output still goes to phase2.md. |
| 3 Inspect | Find selectors | Unchanged |
| 4 Explore | Page-by-page probe, selector swap | **Full dress rehearsal:** walk segments in sequence, observe behavior, revise script (selectors, timing, narration) |
| 5 Build | Emit JSON | Unchanged — but reads Phase 4's *validated* plan |
| 6 Render | Drift check + record | Unchanged |

### Phase 4 mechanism (Path A: extend probe-script model)

Same `Bash` + heredoc approach used today. One change: instead
of writing N small per-page probe scripts, write **one
end-to-end rehearsal script** that walks every segment in order.

Pseudocode of what the rehearsal script captures per segment:

```python
# For each segment in order:
record_observation({
    "index": n,
    "action": "click",
    "selector_attempted": "...",
    "selector_resolved": "...",  # may differ if fallback used
    "wait_for_outcome": "resolved_in_1200ms" | "timeout_after_10s",
    "post_action_state": {
        "url": current_url,
        "title": page.title(),
        "console_errors": [...],
        "key_elements_visible": {...},  # narrative-relevant content
        "layout_metrics": {viewport, scroll, ...},
    },
    "timing": {
        "action_to_dom_settled_ms": ...,
        "subsequent_selector_available_at_ms": ...,
    },
})
```

The agent reads this trace and produces a revised script. If
the rehearsal reveals issues that can be fixed within Phase 4's
authority (see below), the agent revises and re-runs the
rehearsal. If issues exceed authority, BLOCKED with structured
findings as today.

### Authority levels — what Phase 4 can revise

Three categories of fix, in increasing assertiveness:

**Level 1 — Mechanical (no narration changes)**
- Selector swap (already done today)
- Timing adjustment (`pause_after_ms`, `wait_for` timeout)
- Wait-condition refinement (e.g., wait for specific content,
  not just element presence). Refined waits must be VISIBLE-
  waitable — `<option>` elements inside a closed `<select>` are
  hidden in Playwright's model and are refused by the merge (#67)
- Action-KIND change on the same UI element when the scene's
  purpose is unchanged (e.g. click → press-Escape to clear a
  search) — validated against the canonical action contract
  (#67; structural changes to WHAT a scene does remain Level 3)

These are deterministic fixes from observed timing/behavior.
No user judgment needed. PASS outcome.

**Level 2 — Narration regrounding (the high-value change)**
- Replace generic claims with observed specifics ("3 cards",
  not "your cards")
- Drop or rephrase a claim when the predicted state didn't
  match observation
- Stay within the original segment's *intent* and the intent.json
  constraints (audience, tone, focus, excludes)

This is the most valuable level because it closes the
narration-overclaim gap (#49) at a deeper layer than the
prompt-only fix shipped on the previous branch. The narration
becomes grounded in *observed* state, not predicted state.

**Level 3 — Structural changes (NOT in Phase 4's authority)**
- Add new segments to cover transitions
- Drop segments that have nothing to show
- Reorder segments
- Change the demo's overall arc

These remain BLOCKED outcomes that surface to the user via the
triage panel. The user makes the structural call (open
Regenerate, adjust intent.excludes, etc.).

### Convergence guarantees

To avoid the agent revising and re-rehearsing indefinitely:

- **Max iterations**: 3 (rehearse → revise → rehearse → revise →
  rehearse). After that, BLOCKED. About decision quality, not
  time — same cap regardless of demo length.
- **No-progress detection**: if iteration N produces the same
  set of FAIL findings as iteration N-1, BLOCKED immediately.
- **Per-iteration wall-clock cap**:
  `max(60s, segment_count × 8s)`. Scales with the work so long
  demos aren't artificially gated, while short demos still get
  a tight ceiling on pathological agent loops. The 8s/segment
  is a conservative upper bound (real wall-clock per segment is
  typically 3-5s: page load + waits + action).
- **Overall phase ceiling**: 30 min absolute safety net. Should
  never hit in practice; backstop against catastrophic loops or
  hung pages that per-action timeouts somehow miss.

What each layer is protecting against:

- The iteration cap bounds *decision-quality* runaway (agent
  oscillating between fixes).
- The per-iteration cap bounds *agent-thinking-time* runaway,
  which doesn't scale with segment count (input-token bound).
- The overall ceiling bounds *everything else* including
  pathological Playwright behavior the timeouts didn't catch.

Rough wall-clock examples:

| Demo length | Segments | Single rehearsal | 3-iter ceiling |
|---|---|---|---|
| 60-90s (shakedown) | 8 | ~30-40s | ~2 min |
| 5 min | ~30 | ~2-2.5 min | ~7-8 min |
| 10 min | ~60 | ~4-5 min | ~15 min |

### Long-form demos and #50 (section abstraction)

The wall-clock numbers above are for monolithic rehearsals.
That works up to maybe 20-30 segments before it gets fragile —
a mid-walk state surprise (timeout, unexpected redirect, modal
that didn't close) can derail everything downstream of the
problem segment.

For long-form demos, the cleaner shape is **dress-rehearse
per section, not per demo**:

- Each section is ~5-10 segments — back in the shakedown's
  tractable range
- Each section gets its own convergence budget (iteration cap +
  per-iteration wall-clock + ceiling) — same scheme above,
  applied independently
- Sections rehearse **independently**: a failure in section 3
  doesn't waste section 1's rehearsal cost
- Sections could rehearse **in parallel** for further wall-clock
  savings (open question — depends on whether the live app
  handles concurrent Playwright sessions cleanly; some apps
  share session state, some don't)
- Mid-section state changes can't derail the whole demo because
  each section starts from a known nav state

This is an additional reason #50 matters for long-form — it's
not just narrative coherence, it's *rehearsal* coherence. A
monolithic 60-segment rehearsal is structurally fragile; a
sectioned one is naturally checkpointed.

**Implication for the prototype**: validate dress-rehearsal on
the short shakedown scenario first (monolithic is fine for
8 segments). Don't try to combine dress-rehearsal + sections
in the first prototype — that's two architectural changes at
once and they can't be co-validated cleanly. Once dress-rehearsal
is proven on short demos, the per-section adaptation for #50
is straightforward (apply the same convergence scheme per
section, no new design).

### Diff visibility — letting the user see what changed

When Phase 4 revises narration or other plan fields, the user
should be able to see what changed (especially narration —
they may prefer the original).

- `phase4.md` artifact shows the validated plan
- New `phase4-diff.md` artifact shows per-segment field-level
  changes from Phase 3's hypothesis
- GUI: artifact viewer toggles between "validated plan" and
  "diff from hypothesis"
- The segment-row in the segments list flags revised segments
  with a small indicator + tooltip ("Narration regrounded:
  predicted '5 cards', observed '3 cards'")

User can override Phase 4's regrounding via the inline edit
loop (already implemented).

### Recording vs rehearsal: are they the same script?

Open question. Two options:

**A. Rehearsal trace is the recording script.** Phase 4 outputs
a final, validated `demo-script.json` (Phase 5 just rubber-stamps
it). Phase 6 records exactly that. No script-vs-rehearsal drift
possible because they're the same.

**B. Rehearsal verifies; Phase 5 emits the script independently.**
Today's model. Rehearsal is verification; the recording script
is regenerated by Phase 5 from the validated plan.

I lean **A**. It's the natural shape — if the rehearsal succeeded,
preserve exactly what it ran. Phase 5 becomes purely mechanical
(emit + format), which is what we want.

### Cost expectation

Today: full pipeline ~$0.87 for 8-segment demo, Phase 4 ~$0.24.

With dress rehearsal:
- Single successful rehearsal: ~$0.35-0.50 (one bigger probe
  script + slightly more analysis token-count)
- One revision pass: ~$0.55-0.70
- Two revision passes (max): ~$0.75-0.95

Full pipeline goes from $0.87 to maybe $1.10-1.40 in the worst
case. Acceptable, especially given:
- Phase 6 failure rate should drop substantially
- When failures DO happen, they surface in Phase 4 (cheaper) not
  Phase 6 (after spending all upstream phases)
- Narration grounding gets a deeper fix than the prompt-only #49

---

## Prototype plan

Goal: validate that the dress-rehearsal approach produces
demos at least as reliable as today's pipeline, ideally better,
on the same shakedown scenario.

### Scope

**In scope for prototype:**
- New end-to-end rehearsal script generation (replaces today's
  per-page probes)
- Behavioral observation capture
- Level 1 (mechanical) revision authority
- Level 2 (narration regrounding) revision authority
- Max-iteration cap
- Diff artifact (`phase4-diff.md`)
- Run against the saved shakedown fixture

**Out of scope for prototype:**
- Level 3 structural changes (stays BLOCKED as today)
- GUI surfacing of diff (CLI / artifact only for prototype)
- Convergence-detection sophistication beyond max-iteration cap
- Recording-vs-rehearsal script unification (defer the A/B
  decision until prototype data informs it)
- MCP / Playwright-as-tool integration (Path B from
  `ARCHITECTURE_RETHINK.md`)

### Test scenario

The saved fixture at
`fixtures/shakedown-active-sessions-exclude-recently-ended-2026-05-12/`
is the baseline. Run the prototype against the same intent +
URL and compare:

1. **Does the rehearsal complete without BLOCKED on a healthy
   app?** Should match today's pipeline outcome (8/8 PASS).
1. **Does narration become more grounded?** Compare segment
   narration before/after. Look for: dropped overclaim,
   added observed specifics, retained tone/audience.
1. **Are timing observations actually different from defaults?**
   If every segment ends up with the default `pause_after_ms`,
   the observation capture isn't doing useful work.
1. **What does the rehearsal cost?** Measure against the $0.35-
   $0.50 estimate.

Second test: introduce a known break and verify the rehearsal
catches it cleanly. Easiest: change one selector in
`demo-script.json` to something nonsensical and run Phase 4
only against it. Expect FAIL_SELECTOR with a humanized
suggestion.

Third test: introduce a narration overclaim and verify
regrounding fires. Edit phase2.md to claim "10 sessions"
(observed: probably 1-2) and run Phase 4. Expect either
regrounding to the observed count or a FAIL_NARRATIVE with a
clear suggestion.

### Implementation order

1. **Prompt rewrite** — update `src/instantdemo/prompts/phase4.md`
   to specify the full end-to-end rehearsal walk, observation
   format, and revision authority levels. The biggest single
   change.
1. **Findings schema extension** — add fields to the existing
   JSON contract for narration regrounding (`narration_revised:
   bool`, `narration_from`, `narration_to`).
1. **Runner changes** — `src/instantdemo/phases/explore.py`
   parses extended findings; persists `phase4-diff.md`; enforces
   max-iteration cap.
1. **Smoke test** — script that runs Phase 4 only against the
   saved fixture, prints findings + cost.
1. **Compare to baseline** — narration diff, cost diff, timing
   observations.

Estimated effort: 1-2 evenings to a working prototype. Most of
the work is the prompt + the runner-side diff handling.

---

## Open design questions to resolve during prototype

1. **Trace observation format.** What exactly gets captured per
   segment? The pseudocode above is a starting point; the actual
   format should be informed by what the agent finds useful for
   revision decisions.

1. **Narration regrounding boundary.** "Stay within the original
   segment's intent" is fuzzy. Edge case: rehearsal observes
   that the demo'd feature is genuinely broken on the live app
   (button doesn't do what narration says). Is that FAIL_NARRATIVE
   (BLOCKED) or aggressive regrounding ("the button is here but
   it's currently disabled")? Probably FAIL — the demo can't
   show what it claims to show.

1. **Single rehearsal script vs streaming.** A single
   end-to-end script means the agent waits for the whole walk
   to finish before seeing observations. Streaming would let
   the agent revise mid-walk. The latter is more powerful but
   needs Path B (Playwright as agent tool). For prototype,
   single script is fine.

1. **Recording vs rehearsal script unification (A vs B above).**
   Defer until prototype data is in hand.

1. **What to do about Phase 3's selector hypothesis when Phase 4
   has authority to revise?** Phase 3 still produces useful
   structure (test-id conventions, page groupings). But its
   *specific selectors* become less load-bearing. Worth
   re-examining Phase 3's prompt afterward — maybe it becomes
   "structural reconnaissance" rather than "selector inference."

---

## Success criteria

Prototype is considered successful if:

- [ ] Phase 4 rehearsal completes end-to-end on the shakedown
      fixture
- [ ] At least one segment's narration is regrounded based on
      observation (or, if none, that's defensible — narration
      was already grounded)
- [ ] Cost stays within $0.50 for a single-pass rehearsal
- [ ] Introducing a deliberate selector break is caught with
      a clean FAIL_SELECTOR and humanized suggestion
- [ ] Introducing a deliberate narration overclaim either gets
      regrounded or surfaces as FAIL_NARRATIVE with a clean
      suggestion

If two or more of these miss, the prototype has revealed
something we need to redesign. If all five pass, proceed to
GUI integration (diff visibility, regrounded-segment indicator).

---

## Related work

- `ARCHITECTURE_RETHINK.md` — the broader question this design
  is the incremental answer to
- `prompts/phase4.md` — current Phase 4 spec, the document that
  changes most
- `src/instantdemo/phases/explore.py` — Phase 4 runner, changes
  for findings schema + diff artifact
- #48 — the structured-findings + strict-policy work this builds
  on
- #49 — narration grounding; this design extends the fix from
  prompt-only to observation-grounded
- #51 — stale-detection; the dress-rehearsal mechanism is
  exactly the diagnostic primitive #51 would reuse

---

## Addendum (M0, 2026-06-10): the storyboard contract

Phase 4's I/O changed with the storyboard cutover
(`feature/storyboard-contract`; see CLAUDE.md "The storyboard
contract" and PRODUCT_PLAN.md M0):

- **Part 2 of the response format is gone.** The agent's response
  ends with the fenced JSON findings block; the runner merges the
  findings into `.instantdemo/storyboard.json` (selector swaps,
  narration regroundings, status/verification per scene) and renders
  `phase4.md` as a view of the merged document. This removes the
  "two parts must agree" failure mode entirely.
- **New optional `updates` channel per finding**
  (`{"wait_for": [...], "pause_after_ms": n}`): Level-1 timing /
  wait-condition refinements previously survived only in the Part-2
  prose that the Phase 5 agent read. Phase 5 is now a deterministic
  projection, so these refinements MUST flow through findings or
  they'd be silently lost.
- The findings JSON otherwise keeps its index-keyed shape —
  `state.json`'s `explore_findings` and the GUI triage panel are
  unchanged. The convergence loop (MAX_ITERATIONS, failure
  signatures, soft budgets) is unchanged.
