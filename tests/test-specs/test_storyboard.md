# test_storyboard.py Spec

Source: `src/instantdemo/storyboard.py`
Test: `tests/test_storyboard.py`

## Methods not tested (and why)

| Method | Reason |
|---|---|
| `path_for()` | One-line path join, no branching. |
| `_now()` | Wraps datetime.now; correctness is stdlib's. |

## new_document() / add_scene() / save() / load()

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| D1 | Two scenes added to a fresh document | ids are s1, s2; next_scene_seq advances to 3 | Unstable/colliding scene ids — future notes, sections, and versioned takes attach to the wrong scene |
| D2 | Scene removed, then a new scene added | New scene gets s3; s1 not reused | Deleted scene's id resurrected — stale references (revisions, notes) silently point at a different scene |
| D3 | Scenes reordered, then save + load | index recomputed 1..N in array order; updated_at stamped | Phase 4 findings are index-keyed — wrong indexes mis-apply selector swaps to the wrong scene |
| D4 | load() on a dir without storyboard.json | RuntimeError with the migration message | Legacy projects fail with an inscrutable traceback instead of the re-run instruction |

## normalize_candidates()

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| N1 | Bare string input | Returns single-element list | Phase 3 agents emitting strings (not arrays) crash the merge instead of being normalized |
| N2 | List with whitespace and empty entries | Stripped, empties dropped, order kept | Empty selector candidates reach the renderer and burn its per-candidate timeout budget |
| N3 | None / empty string | Returns [] | Optional wait_for treated as present — validators pass scenes that the renderer can't wait on |

## extract_json_block()

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| J1 | Prose followed by one fenced json block | Returns parsed dict | Agents that reason before the block (explicitly allowed by prompts) fail parsing |
| J2 | Invalid block then valid block | Skips broken, returns the valid one | One malformed example block in agent prose kills the whole phase |
| J3 | No fenced block | Returns None | Caller can't distinguish "no JSON" from crash; retry turn never triggers |
| J4 | Fenced block containing a JSON array | Returns None (objects only) | A stray array (e.g. example selectors) masquerades as the payload and corrupts the merge |

## validate_storyboard(stage="planned")

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| VP1 | Well-formed 2-scene document | No problems | Valid output rejected — every Phase 2 run fails |
| VP2 | Scene with action "wait_for_selector" | Problem naming unknown action + allowed list | The #57 bug class returns: invented actions reach the renderer and crash mid-recording |
| VP3 | Duplicate scene ids | Problem flagging the duplicate | Merges by id (Phase 3) write one agent payload into two scenes |
| VP4 | Document with zero scenes | Single "no scenes" problem | Empty plan flows downstream; Phase 4 rehearses nothing and Phase 5 emits an unrenderable script |
| VP5 | narration is None | Problem requiring string narration | TTS layer crashes on None instead of treating "" as silent |

## validate_storyboard(stage="hypothesized")

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| VH1 | click scene with no selector | Problem requiring non-empty selector candidates | Unactionable scenes pass to Phase 4, wasting a full rehearsal iteration to discover it |
| VH2 | click scene with selector candidates | No problems | Valid Phase 3 output rejected — phase can never complete |
| VH3 | scroll scene with no extra fields | No problems | Actions with no required fields wrongly demand them |
| VH4 | pause_after_ms as string "1500" | Problem requiring integer | String pause reaches renderer arithmetic and crashes mid-recording |
| VH5 | evaluate scene with no expression | Problem requiring expression | Renderer dispatches evaluate with nothing to run |

## validate_storyboard(stage="verified")

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| VV1 | Scene still status=planned/hypothesized | Problem: must be verified or warn | Unverified scenes render — exactly the drift Phase 4 exists to prevent |
| VV2 | All scenes verified or warn | No problems | Phase 5 permanently blocked after clean rehearsals |

## to_demo_script()

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| P1 | Single wait_for candidate | Projects as bare string | demo-script.json shape drifts from today's convention; downstream tooling/hand-edits break |
| P2 | Multi-candidate selector | Projects as array, primary first | Fallback selectors lost — renderer loses its recovery path |
| P3 | Verified 3-scene storyboard | Projection passes actions.validate_segments | Phase 5 emits scripts its own renderer rejects — pipeline dead-ends at the last step |
| P4 | Envelope fields | title from doc, 1280x720 default, pause carried | Renderer falls back to wrong resolution/title; pacing lost |
| P5 | Scene with notes/status/verification | None of them appear in segments | Internal bookkeeping leaks into the render contract (and into anything users hand-edit) |

## render_phase2_view() / render_phase3_view() / render_phase4_view()

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| W1 | Phase 2 view of a 2-scene doc | ANSWER block present with tone/audience/terminology; `### Segment 1 — title` heading; (silent) for empty narration; Target line | checkpoints.parse_answer_block and the GUI's MarkdownView segment renderers break — CLI re-runs lose user inputs, GUI shows broken layout |
| W2 | Phase 2 view round-trip | checkpoints.parse_answer_block recovers the answers | Legacy CLI edit path (tone/audience edits between runs) silently stops feeding forward |
| W3 | Phase 3 view with fallbacks/pause/notes | Selector + fallbacks rendered as labeled rows | GUI EditorPane shows raw/garbled selector data; humans can't review the hypothesis |
| W4 | Phase 4 view with findings + revision | findings JSON block present; Verified line; Revised line with from→to | phase4.md loses the findings block (smoke asserts it) and reviewers can't see what the rehearsal changed |
