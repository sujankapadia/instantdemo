# test_storyboard_routes.py Spec

App: `instantdemo.server.app` (storyboard router, M2)
Test: `tests/test_storyboard_routes.py`

## GET /api/project/storyboard

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| SG1 | Project with a storyboard.json | exists=true, storyboard.scenes round-trip with ids/status | StoryboardView renders nothing — the M2 surface is dead |
| SG2 | Project without storyboard.json | 200 with exists=false (not 404) | Frontend error state instead of the planned placeholder on fresh projects |

## PATCH /api/project/storyboard/scenes/{id}

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| SP1 | Edit narration of an existing scene | 200; narration updated on disk; revision appended with type=narration, phase=0, iteration=0, from=old text; updated_at bumped | Gate edits silently lost — user approves text that never reaches the render |
| SP2 | Edit when state.json has phase-4 explore_findings | phase4.md re-rendered containing the new narration | Power-mode artifact diverges from the canonical doc — reviewer reads stale text |
| SP3 | Unknown scene id | 404 | Edits write to nothing while the UI reports success |
| SP4 | No storyboard.json | 404 with the run-the-pipeline message | Confusing 500 on fresh projects |
| SP5 | No-op (same narration) | 200; NO revision appended; file not rewritten | Revision history fills with phantom user edits |
| SP6 | Active run in progress (run_manager.active running; requires the app lifespan, which creates run_manager — TestClient must run as a context manager) | 409 | Concurrent write corrupts storyboard.json mid-[2,3,4] run |

## /api/project marker exposure

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| SM1 | state.json without storyboard_approved | /api/project returns storyboard_approved=false | Legacy projects render an approve gate over a finished video (visibility rule also guards via phase-6 check, but the default must be sane) |
| SM2 | state.json with storyboard_approved=true | /api/project returns true | Gate never disappears after approval |
