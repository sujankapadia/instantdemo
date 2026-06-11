# test_scoped_replan.py Spec

Source: `phases/narrate.py` (scoped re-plan, M5b) + `server/routes/runs.py` (pending_scope)
Test: `tests/test_scoped_replan.py`

## Methods not tested (and why)

| Method | Reason |
|---|---|
| `_build_scoped_prompt` | Prompt-text assembly; quality verified by the live scoped smoke |
| `_run_scoped` end-to-end | Needs the SDK; the route/pure pieces below are its load-bearing parts, and the live smoke covers the rest |

## replace_chapter_scenes()

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| S1 | Replace middle chapter (B of A,B,C) with 3 new scenes | New scenes sit between A and C with fresh ids (next_scene_seq continued); A and C scene objects untouched; after save, indices contiguous | The revised chapter lands in the wrong place or renumbers the film |
| S2 | Old chapter ids retired | None of the replaced scenes' ids appear in the doc; next_scene_seq never reused them | Id collision corrupts thumbnail binding and revisions |
| S3 | Replace the OPENING chapter | New block first, rest untouched | Off-by-one at the film's start |
| S4 | Replace the CLOSING chapter | New block last | Off-by-one at the film's end |
| S5 | Unknown chapter name | ValueError | Silent no-op masquerading as a revision |
| S6 | Replaced doc passes planned-stage validation (contiguity preserved) | validate_storyboard == [] | A scoped re-plan can emit a storyboard later phases reject |

## _scoped_validator()

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| SV1 | Valid chapter payload (all scenes in scope) | No problems | Valid re-plans burn the corrective retry |
| SV2 | A scene with section != scope | Problem naming the rule | The agent quietly rewrites a different chapter |
| SV3 | Unknown action / missing title / >10 scenes | Problems | Garbage scenes reach the storyboard |

## pending_scope lifecycle (route level)

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| P1 | Scoped [2,3,4] run started | state.pending_scope == {section, instruction} | The approve leg records the wrong span (full re-record) |
| P2 | Unscoped [2,3,4] (or regenerate) started after a scoped leg | pending_scope cleared | A later unrelated approve silently scope-records against a stale chapter |
| P3 | [5,6] run with no own scope while pending_scope set | Context receives the pending scope | Same as P1 — the handoff is the point |
