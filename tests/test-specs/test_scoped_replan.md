# test_scoped_replan.py Spec

Source: `phases/narrate.py` (scoped re-plan, M5b) + `server/routes/runs.py` (pending_scope)
Test: `tests/test_scoped_replan.py`

## Methods not tested (and why)

| Method | Reason |
|---|---|
| `_build_scoped_prompt` | Prompt-text assembly; quality verified by the live scoped smoke |
| `_run_scoped` end-to-end | Needs the SDK; the route/pure pieces below are its load-bearing parts, and the live smoke covers the rest |
| explore.run scoped shot-clearing | Inline in the runner (keeps pngs whose stem is a live scene id); exercised by the live scoped smoke |

## Scoped phases 3+4

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| G1 | gather._make_validator with scope_ids | Payload covering exactly the chapter ids passes; full-doc payload rejected (unknown ids); missing chapter id rejected | Phase 3 silently re-enriches verified scenes — or skips the new ones |
| E1 | merge_findings_into_storyboard with scope_indices | In-scope finding applies; out-of-scope finding warned + scene untouched | The rehearsal rewrites verified, recorded scenes outside its authority |

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

## Scoped record + splice (render layer, pure parts)

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| T1 | rebuild_section_timing: middle chapter, new shorter than old | Pre rows byte-equal; chapter rows fresh (slots cumulative from pre end, audio + recorded durations); tail rows keep durations, shift by delta, re-index; total = cursor | Click-to-seek and future splices land mid-frame everywhere after the chapter |
| T2 | rebuild_section_timing: opening chapter (no pre) and closing chapter (no tail) | Cursor starts at 0 / no tail rows; totals correct | Boundary chapters corrupt the timeline |
| P4 | _section_render_plan: aligned project (counts match, contiguous chapter, recorded durations) | Returns (start, end, old_len) | Scoped renders never happen — every revision is a full re-record |
| P5 | _section_render_plan: prefix/tail counts diverge from old timing (the m5b-scoped live case) | None (full-record fallback), no raise | Splice against a mismatched film corrupts the demo |
| P6 | _section_render_plan: no film/timing, unknown chapter, scoped flag absent | None each | Same as P5 |

## pending_scope lifecycle (route level)

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| P1 | Scoped [2,3,4] run started | state.pending_scope == {section, instruction} | The approve leg records the wrong span (full re-record) |
| P2 | Unscoped [2,3,4] (or regenerate) started after a scoped leg | pending_scope cleared | A later unrelated approve silently scope-records against a stale chapter |
| P3 | [5,6] run with no own scope while pending_scope set | Context receives the pending scope | Same as P1 — the handoff is the point |
