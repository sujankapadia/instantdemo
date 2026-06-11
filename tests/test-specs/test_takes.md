# test_takes.py Spec

Source: `src/instantdemo/takes.py` (M4 — versioned takes)
Test: `tests/test_takes.py`

## Methods not tested (and why)

| Method | Reason |
|---|---|
| `takes_dir` / `take_video_path` | One-line path joins |

## snapshot / numbering / retention

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| T1 | Snapshot a project with all four artifacts | takes/v1/ holds demo.mp4 + 3 JSONs + meta.json {n, label, created_at}; returns 1 | Takes silently empty — "your previous version is kept" is a lie |
| T2 | Snapshot a project missing demo.mp4 (pre-render) | v1 holds the JSONs, no video, no raise | Pre-render revisions (gate edits) can't snapshot |
| T3 | Three snapshots → numbering | v1, v2, v3; next_take_number scans dirs (no counter file) | Take numbers collide after manual dir deletion — restore overwrites the wrong take |
| T4 | Five snapshots with videos | Only the newest 3 keep demo.mp4; ALL five keep JSON + meta; prune returns the pruned numbers | Disk fills with videos, or text history lost with the video |
| T5 | list_takes ordering + fields | Newest first; {n, label, created_at, video_exists} correct incl. pruned takes (video_exists false) | The Previous-version toggle shows wrong/unplayable takes |
| T9 | is_current flag | A post-render snapshot (video byte-copy of current demo.mp4) has is_current=true; after the project's film changes, is_current=false | "Previous version" offers a no-op comparison between identical videos right after a render |

## restore

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| T6 | Restore v1 after project files changed | All four project files byte-equal v1's copies | Restore is partial — film and script from different takes (incoherent project) |
| T7 | Restore a pruned-video take | ValueError naming the prune policy | A film-less restore silently breaks the current demo |
| T8 | Restore a nonexistent take | ValueError | 500s instead of a clean 4xx at the route layer |
