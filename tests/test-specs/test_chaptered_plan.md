# test_chaptered_plan.py Spec

Source: `phases/narrate.py` (M7 chaptered cold start: outline →
chapter loop → continuity pass)
Test: `tests/test_chaptered_plan.py`

## Methods not tested (and why)

| Method | Reason |
|---|---|
| `_build_outline_prompt` / `_build_chapter_plan_prompt` | Prompt assembly; quality verified by the live cold-start gate |
| Real SDK behavior | Live cold start; tests monkeypatch run_structured_query (FakeResult mirrors the ResultMessage fields summarize/record read) |

## _validate_outline()

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| O1 | Valid outline (3 chapters, names/purposes/est) | No problems | Valid outlines burn the corrective retry |
| O2 | 1 chapter / 13 chapters | Problem (2–12 rule) | Degenerate arcs (everything one chapter) or runaway fragmentation |
| O3 | Duplicate names, missing purpose, bad est_scenes | Problems each | Duplicate chapter names break contiguity downstream; unscoped chapters plan blind |

## run() — the chaptered build (run_structured_query monkeypatched)

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| CB1 | Canned outline (3 chapters) + per-chapter payloads | Doc has all scenes in outline order; sections contiguous; ids sequential; planned-stage valid; phase2.md view written | The cold start builds a board later phases reject |
| CB2 | Validator passed to chapter k pins section to chapter k's name | A payload with a wrong section fails validation (the canned harness asserts the validator it received rejects it) | A chapter call writes scenes into another chapter |
| CB3 | Chapter-plan prompt content | Contains the full outline, the chapter's purpose, and the previous chapter's final narration (opening chapter: the opens-the-film line instead) | Chapters planned blind to the arc — the disjointed-film failure mode |
| CB4 | Cost aggregation | record_phase_result called with cost_usd_total == sum of all (K+2) call costs | Long-form cost reporting understates by ~K× |
| CB5 | chapter_progress events | Emitted per chapter with current/total/name | The GUI shows a silent multi-minute planning phase |

## Continuity pass

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| CN1 | Canned rewrites {"2": ...} | Scene 2's narration replaced in the doc; others untouched | The pass silently does nothing (or the wrong scene) |
| CN2 | Empty rewrites map | Accepted (no validation problems), no mutation | "Reads fine" burns the corrective retry |
| CN3 | Markup / out-of-range rewrites | Rejected by the wrapper (style-pass rules intact) | Markup reaches narration; rewrites land on phantom scenes |
