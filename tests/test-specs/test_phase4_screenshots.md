# test_phase4_screenshots.py Spec

Source: `src/instantdemo/phases/explore.py` (+ `server/routes/runs.py` for the gate marker)
Test: `tests/test_phase4_screenshots.py`

## Methods not tested (and why)

| Method | Reason |
|---|---|
| `_ensure_screenshots()` | One corrective SDK turn + dir re-scan; covered live by smoke_phase4_rehearsal 5a |
| `rehearsal_dir()` | One-line path join |
| watcher reuse | `analyze.watch_screenshots` is a thin loop over `new_screenshots`, already spec'd in test_phase1_explore.md NS1-NS3 |

## link_rehearsal_screenshots()

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| L1 | Shots exist for scenes 1 and 3 of 3 (fresh doc: ids == positions) | Scenes 1+3 get rehearsal_screenshot "s1.png"/"s3.png"; scene 2 has no key; returns the two names | Storyboard cards show wrong/missing thumbnails — the gate review loses its visual grounding |
| L2 | Scene carries a stale rehearsal_screenshot from a prior run; no file on disk | Key POPPED | Gate shows a prior run's screen for a re-rehearsed scene — user approves against wrong imagery |
| L3 | Rehearsal dir missing entirely | No keys set, returns [], no crash | Phase 4 crashes post-merge when the agent saved nothing |
| L4 | Ids ≠ positions (M5b: scoped re-plan inserted s5 at position 2) | Binding is BY ID: scene s5 at index 2 links "s5.png", NOT "s2.png" | Post-revision thumbnails bind to the wrong scenes — the gate reviews chapter A with chapter B's screens |

## runs._storyboard_marker() (gate marker truth table — M2-c)

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| GM1 | phases=[1] | None (untouched) | Exploration run wrongly resets/sets approval — gate shows at the wrong stage |
| GM2 | phases=[2,3,4] | False | Rehearsal leg doesn't reset approval — stale approve state skips the gate |
| GM3 | phases=[4] | False | A re-rehearse leaves old approval standing; user never re-reviews changed scenes |
| GM4 | phases=[5,6] | True | Approve run doesn't flip the marker — gate re-appears over the rendering video |
| GM5 | phases=[1,2,3,4,5,6] | True | Regenerate (single run, no gate) leaves approved=false — phantom gate over finished video |
| GM6 | phases=[6] | True | Targeted re-render re-presents an approve CTA |
