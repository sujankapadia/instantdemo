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

## Phase 3/4 chapter loops (run_structured_query / run_query_on_client monkeypatched)

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| GL1 | gather.run on a 3-chapter board | One call per chapter (session ids -c1..-c3); each validator pins that chapter's ids; doc hypothesized-valid after the loop; aggregate cost recorded | Phase 3 regresses to whole-board prompts — the length ceiling returns |
| GL2 | gather scoped-validator dry-run during the loop | Chapter 1's validation passes while later chapters are still bare (scoped trial, not whole-doc) | Cold-start chapter 1 can never validate — the loop is unrunnable |
| EL1 | explore.run on a 3-chapter board, all PASS | One section-runner per chapter in order; combined explore_findings carries all chapters' segments (global indices); scenes verified | Rehearsal regresses to one accumulating session — the real ceiling returns |
| EL2 | Chapter 2 BLOCKED | Chapter 2 retries once in ITS session (convergence loop), then same-signature stop; its findings merged (failure visible at the gate); chapter 3 never rehearsed; run raises | A broken chapter's successors rehearse against a false prefix |
| EL3 | Scoped revision (section_scope set) | Single-section loop; out-of-scope thumbnails kept (M5b behavior intact) | The revision flow breaks under the M7 refactor |

(GL1/GL2 share one test — the canned harness asserts in-loop validation; EL3 is covered by the existing M5b suite (test_scoped_replan) remaining green plus the live rehearsal smoke.)
