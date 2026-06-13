# test_stale_rail.py Spec

Source: `src/instantdemo/server/routes/runs.py` (`_mark_stale_phases` —
M8/#85 item 4) + `src/instantdemo/state.py` (`phase_run` stale pop)
Test: `tests/test_stale_rail.py`

## Why

A revision leg ([2,3,4]) leaves phases 5/6 showing "completed" from
the previous render — the rail reads "all done" at the gate, and the
frontend's in-memory stale logic dies on page reload. The flag is
persisted in state.json: start_run marks completed phases LATER than
the run's highest phase with `stale: true`; clearing happens when the
phase's entry is rewritten (start_run pending reset) or when it runs
through any path (phase_run pops the flag).

## _mark_stale_phases / phase_run

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| S1 | [2,3,4] run; phases 1–6 all completed | 5 and 6 get stale:true; 2–4 are reset to pending WITHOUT stale; 1 untouched (still completed, no stale) | The rail lies "all done" at the gate after a revision — the M5b L5 complaint, surviving reloads |
| S2 | [1] run; 2–6 completed | 2–6 all stale (everything downstream of a re-explore is suspect) | A re-explored app keeps a storyboard the rail vouches for |
| S3 | [5,6] run after S1's marks | start_run's pending reset rewrites 5/6 entries — stale gone (the approve-leg edge works for free) | Freshly recorded phases wear stale dots forever |
| S4 | Later phase has status error / canceled / pending | NOT marked stale (only completed lies) | Noise: error phases double-flagged; pending phases gain meaningless flags |
| S5 | phase_run re-runs a phase whose entry carries stale:true | Flag absent while in_progress and after completion (popped at start; not resurrected by the completion merge) | CLI `instantdemo phase N` re-runs leave a completed-AND-stale contradiction |
