# test_revise.py Spec

Source: `src/instantdemo/revise.py` + `server/routes/revise.py` (M4 style/pace pass)
Test: `tests/test_revise.py`

## Methods not tested (and why)

| Method | Reason |
|---|---|
| `_build_prompt` | Prompt-text assembly; quality verified by the live style smoke |
| Real SDK interpretation | Live smoke territory (nondeterministic); route tests monkeypatch `run_structured_query` |

## validate_style_payload

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| V1 | Valid rewrite payload | No problems | Valid revisions burn the corrective retry |
| V2 | rewrite with markup in narration ("**bold**", "```", leading "-") | Problem per offender | Markup is narrated aloud and shown in captions |
| V3 | rewrite index out of range / non-integer key / empty text | Problems named | Rewrite lands on the wrong scene or wipes one |
| V4 | pace_factor outside 0.6–1.5, or exactly 1, or missing for kind=pace | Problems | Absurd pacing applied, or a no-op spends a re-render |
| V5 | Unknown kind; voice without suggestion; rewrites on kind=pace | Problems | Misshapen interpretations execute |

## apply helpers

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| A1 | apply_rewrites changes only listed segments; returns sorted 0-based changed; identical text not counted | Exact diff semantics | play-the-change seeks to the wrong scene |
| A2 | apply_pace scales pauses (rounded int), skips 0/None pauses, returns changed | Pause-less segments untouched | Pauseless segments gain phantom pauses |

## POST /api/project/revise (route; SDK + re-render monkeypatched)

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| R1 | rewrite instruction (canned payload) | Take snapshotted BEFORE mutation (take's script = original); demo-script updated; storyboard synced w/ revision reason = instruction; re-render called with take_label=None; response carries first_changed_index + take_n | The core flow — any ordering break corrupts history or double-snapshots |
| R2 | pace slower (1.2) | Pauses scaled; re-render called; needs_rerecord false | Slower asks silently need a re-record |
| R3 | pace faster (0.8) | Pauses scaled; re-render NOT called; needs_rerecord true | A re-record-needing change spends an audio render that desyncs |
| R4 | voice / structural / unclear kinds | No take, no mutation, no re-render; explanation + suggestion returned | Non-executable asks mutate the film |
| R5 | 409 matrix: active run; revise_busy; AND start_run refuses while revise_busy | All three 409 | The shared dispatcher races |
| R6 | Scene/segment count mismatch | storyboard_synced false; script still updated | Unequal lists index-mapped — wrong scene revised upstream |
| R7 | No film yet (missing demo.mp4) | 404 plain message | Confusing failure pre-render |
