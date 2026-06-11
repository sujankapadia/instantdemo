# Plan: Dress-rehearsal Phase 4 prototype

## Context

After the M3 shakedown and the #5 / #49 prompt fixes, we surfaced
a deeper question: is the 6-phase plan-then-reconcile architecture
the right shape, or is there a simpler / more reliable approach?

`ARCHITECTURE_RETHINK.md` (committed on `feature/gui`) explores a
full explore-first inversion. `DRESS_REHEARSAL_DESIGN.md` (this
branch, `feature/dress-rehearsal`) lands on an incremental
synthesis: keep the upfront codebase analysis, but **upgrade
Phase 4 from page-by-page selector probing to a full end-to-end
headless dress rehearsal** that walks every segment in sequence
and gains authority to reground narration based on observed state.

Goal of this prototype: validate that the dress-rehearsal approach
produces demos at least as reliable as today's pipeline — ideally
better — on the saved shakedown fixture, before committing to
broader refactoring. Most of the work is additive on top of Phase
4's existing probe-script-via-Bash mechanism.

## Approach

Five sequential steps. Each is independently verifiable. Stop and
inspect after each step rather than batching.

### 1. Rewrite the Phase 4 prompt

**File:** `src/instantdemo/prompts/phase4.md`

The prompt is the heart of the change. Today it specifies
**page-by-page probing**. The rewrite specifies an **end-to-end
rehearsal walk** with three authority levels (Mechanical /
Narration regrounding / Structural-stays-BLOCKED), per the design
doc's section "Authority levels — what Phase 4 can revise."

Key changes:
- Workflow shifts from "group segments by page, one probe per
  page" to "one rehearsal script that walks every segment in
  sequence as the renderer will"
- Observation capture per segment: action, resolved selector,
  wait outcome, post-action state (url, key elements visible,
  console errors), timing
- Authority Level 1: mechanical fixes (selector swap, timing,
  wait conditions) — already partly authorized today
- Authority Level 2: narration regrounding — new authority,
  must stay within `intent` constraints; emit `narration_from`
  / `narration_to` in findings
- Authority Level 3: structural changes (drop / add / reorder
  segments) → stays BLOCKED with humanized suggestion
- Output format unchanged in shape (JSON block + markdown);
  schema extended with three new optional per-segment fields

### 2. Extend the findings schema

**Files:**
- `src/instantdemo/server/routes/project.py` — `PhaseState`
  model has `model_config = ConfigDict(extra="allow")` so no
  strict change needed, but document the new fields in the
  prototype's typed view if one exists

Schema additions (per-segment, all optional):
- `narration_revised: bool` — true if Phase 4 changed the
  narration text
- `narration_from: str` — original narration (when revised)
- `narration_to: str` — replacement narration (when revised)

PASS + `narration_revised: true` is the analog of today's
PASS + `selector_swapped: true` — a fix, not a warning.

### 3. Rewrite the Phase 4 runner for multi-iteration + diff

**File:** `src/instantdemo/phases/explore.py`

Current shape (lines 118–186): single-pass `run(context)` —
build prompt, invoke agent once, parse findings, record, raise
on BLOCKED.

New shape: wrap the query / parse / record cycle (lines 136–168
of current `explore.py`) in a convergence loop. Pseudocode:

```python
prior_findings_signature = None
for iteration in range(1, MAX_ITERATIONS + 1):
    start = time.monotonic()
    iter_budget_s = max(60, segment_count * 8)
    text, result = await run_query_on_client(...)  # existing helper
    findings = _parse_findings(text)
    record_phase_result(context, result, iteration=iteration)
    overall = _findings_overall(findings)
    if overall == "OK":
        break
    sig = _failure_signature(findings)
    if sig == prior_findings_signature:
        break  # no progress, stop
    if time.monotonic() - start > iter_budget_s:
        break  # per-iteration cap hit
    prior_findings_signature = sig

# After loop: write phase4-diff.md, raise on BLOCKED as today
```

Three convergence layers per the design doc:
- **Iteration cap:** `MAX_ITERATIONS = 3`
- **No-progress detection:** new `_failure_signature(findings)`
  helper — frozenset of `(index, status)` tuples for FAIL_*
  segments. Identical signature across iterations → stop.
- **Per-iteration wall-clock:** `max(60, segment_count * 8)`
  seconds. Computed from Phase 3's segment count.
- **Overall phase ceiling:** 30 min, applied externally
  (server timeout, not in this runner — leave as a future
  concern; the per-iteration cap × 3 keeps this well below).

Reused as-is (no changes needed):
- `_build_prompt()` (line 56)
- `_parse_findings()` (line 74) — same JSON block regex
- `_findings_overall()` (line 89) — same deterministic policy
- `run_query_on_client()` from `phases/__init__.py` — handles
  session_id, dispatcher.current_phase, ResultMessage, cost
  delta tracking. Costs accumulate naturally across iterations
  via `dispatcher.session_cost_totals` and the merge-style
  `state.record_phase_metrics()`.

New helpers in `explore.py`:
- `_failure_signature(findings) -> frozenset` — for no-progress
  detection
- `_write_diff_artifact(context, original_segments, final_segments,
  final_findings) -> None` — writes `.instantdemo/phase4-diff.md`
  by reading the Phase 3 markdown segments and comparing to the
  validated state in findings. Format: a small markdown table
  per changed segment listing field, before, after. Skipped if
  no changes.

### 4. Add a Phase-4-only smoke test

**File:** `scripts/smoke_phase4_rehearsal.py` (new)

Template: `scripts/smoke.py` (the Phase 2 smoke). Same shape:
spawn `instantdemo serve` against a saved fixture, POST
`/api/runs` with `{"phases": [4], "url": "..."}`, stream SSE
until terminal, assert state.json metrics and findings.

Fixture: `fixtures/shakedown-active-sessions-exclude-recently-ended-2026-05-12/`
(the one already saved). Restore to a temp dir, point the smoke
at it.

Assertions:
- Run reaches terminal state without RuntimeError
- `state.json` `phases.4.explore_overall == "OK"`
- `phase4.md` exists and contains the JSON findings block
- `phase4-diff.md` exists (whether or not anything changed —
  the file should be emitted even on a no-revision run, with
  a note saying so)
- Cost is within $0.50 ceiling for single-iteration success
  (warn if exceeded, don't fail — cost shape is part of what
  we're measuring)

### 5. Run, compare, iterate

Three scenarios per the design doc's success criteria:

**5a. Happy-path rehearsal on healthy app**
- Restore the shakedown fixture
- Start the active-sessions app (claude-code-analytics on
  8000/5173)
- Run the smoke
- Verify: rehearsal completes, narration is at least as
  grounded as the baseline phase2.md, no FAIL surfaces

**5b. Deliberate selector break**
- Restore the fixture
- Edit one segment's selector in `demo-script.json` to
  something nonsensical (e.g., `[data-testid="does-not-exist"]`)
- Run Phase 4 only
- Verify: clean FAIL_SELECTOR with humanized suggestion, no
  crash, BLOCKED outcome

**5c. Deliberate narration overclaim**
- Restore the fixture
- Edit `phase2.md` to claim something the live app contradicts
  (e.g., "10 active sessions" when there are 1-2)
- Run Phase 4 only
- Verify: either narration regrounded (PASS + narration_revised)
  or clean FAIL_NARRATIVE with humanized suggestion

Document results in a new `fixtures/dress-rehearsal-shakedown-<date>/`
fixture (matching the existing fixture naming) so we have a
reproducible comparison point.

## Critical files

**Modified:**
- `src/instantdemo/prompts/phase4.md` — rewrite for end-to-end
  rehearsal + three authority levels
- `src/instantdemo/phases/explore.py` — wrap single-pass logic
  in convergence loop, add `_failure_signature` +
  `_write_diff_artifact` helpers

**Added:**
- `scripts/smoke_phase4_rehearsal.py` — Phase 4 smoke test
- `.instantdemo/phase4-diff.md` — new per-run artifact (written
  by runner, not committed)

**Read-only (existing utilities reused):**
- `src/instantdemo/phases/__init__.py` — `Context`, `run_query_on_client()`,
  `record_phase_result()`, `phase_artifact()`. No changes.
- `src/instantdemo/agent_client.py` — `PHASE_TOOLS["phase4"]` =
  `{"Read", "Bash"}`. Unchanged.
- `src/instantdemo/state.py` — `record_phase_metrics()` merges
  dict-style, so cumulative iteration costs accumulate
  naturally. No changes.
- `src/instantdemo/prompts/__init__.py` — `prompts.load("phase4")`.
  Unchanged.
- `scripts/smoke.py` — template for the new smoke script.

## Verification

Plumbing:
- `python -c "from instantdemo.phases import explore"` — import
  cleanly
- Run the new smoke script against the saved shakedown fixture
  with the app up; expect OK overall
- Inspect `phase4.md` for proper structured findings, narration
  changes if any
- Inspect `phase4-diff.md` for legibility

End-to-end (manual, with `instantdemo serve --project /tmp/shakedown-restore`):
1. Restore fixture, start server (port 8771, no ANTHROPIC_API_KEY)
2. Trigger Phase 4 only from GUI with details toggle on
3. Observe agent log: should show one Bash invocation with a
   bigger end-to-end script (not N small per-page probes)
4. Inspect phase4.md and phase4-diff.md
5. Repeat with deliberate breaks (5b, 5c above)

## Out of scope for this prototype

(Explicit list to prevent scope creep — these are documented
in `DRESS_REHEARSAL_DESIGN.md` as deferrals.)

- Level 3 structural changes (drop / add / reorder segments) —
  stays BLOCKED as today
- GUI surfacing of `phase4-diff.md` (artifact-viewer toggle,
  segment-row regrounding indicator) — defer until CLI/artifact
  results validate the approach
- Recording-vs-rehearsal script unification (Option A vs B in
  the design doc) — Phase 5 still emits the script independently
  for this prototype; revisit after prototype data is in hand
- Section-based rehearsal (per-section convergence) — defer
  until short-demo prototype proves out; don't combine with #50
- MCP / Playwright-as-tool integration (Path B) — Path A
  (extend probe-script model) is sufficient for this prototype
- Convergence sophistication beyond max-iteration + signature
  no-progress — e.g., partial-progress credit, adaptive
  iteration budget. Defer.

## Success criteria (from design doc)

Prototype is successful if:

- [ ] Rehearsal completes end-to-end on the shakedown fixture
- [ ] At least one segment's narration is grounded by
      observation (or, if none, the original narration was
      already observation-equivalent — defensible)
- [ ] Cost stays within $0.50 for single-pass rehearsal
- [ ] Deliberate selector break → clean FAIL_SELECTOR with
      humanized suggestion
- [ ] Deliberate narration overclaim → regrounded or clean
      FAIL_NARRATIVE with humanized suggestion

If 2+ miss, the prototype has revealed something needing
redesign. If all 5 pass, proceed to GUI integration (diff
visibility, regrounded-segment indicator) — a separate change.
