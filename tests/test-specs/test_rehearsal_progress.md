# test_rehearsal_progress.py Spec

Source: `src/instantdemo/phases/analyze.py` (`parse_progress_line`,
`tail_progress_log` — M8/#85 item 3) + `src/instantdemo/phases/explore.py`
(prompt contract)
Test: `tests/test_rehearsal_progress.py`

## Why

The scoped prefix replay produces no thumbnails — minutes of dead
air. The agent's Bash stdout is invisible to the runner (the SDK
message stream carries text and tool-use blocks, never tool results),
so the rehearsal script APPENDS one line per step to
`{rehearsal_dir}/progress.log` (`setup k/N` during prefix replay,
`scene s<id>` per in-scope scene) and a tailer coroutine — the same
filesystem pattern as watch_screenshots — emits rehearsal_progress
SSE events. Tolerance is the design: the agent may never write the
file; nothing errors and the header falls back to the two-stage
sentence.

## Rows

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| P1 | `parse_progress_line("setup 3/7")` | `{"kind": "setup", "current": 3, "total": 7}` | Setup ticks never reach the header — the dead air this item exists to fill |
| P2 | `parse_progress_line("scene s12")` | `{"kind": "scene", "scene_id": "s12"}` | Scene ticks lost; the setup sentence lingers into the chapter |
| P3 | Malformed lines ("", "setup x/y", "banana", "setup 3/0") | None each, no raise | An agent's creative formatting crashes the tailer task |
| P4 | Tail a file appended in two chunks, the second write split mid-line | Events in order; the partial line held until its newline arrives | Half-parsed lines emit garbage events |
| P5 | File never exists for several polls | No events, no crash, keeps polling | A non-complying agent (or a pre-M8 prompt) kills the watcher |
| P6 | File truncated between polls (genuinely smaller — replaced with fewer bytes) | Offset resets to 0; subsequent lines emitted | A second convergence iteration's fresh log silences progress. (Detection is by shrinking size; a same-length in-place rewrite is not detected — acceptable, since runs unlink the log rather than rewrite it in place.) |
| P7 | `_build_initial_prompt` scoped variant mentions progress.log + `setup k/N`; the phase4 template carries the per-scene contract | Both substrings present | The contract silently drops out of the prompt — feature dead with no test failing |
