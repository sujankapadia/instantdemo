# test_takes_routes.py Spec

App: `instantdemo.server.app` (takes router, M4)
Test: `tests/test_takes_routes.py`

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| R1 | GET /api/project/takes after two snapshots | Newest-first list with n/label/video_exists | Previous-version toggle renders nothing |
| R2 | GET /takes/{n}/video for an existing take | 200 video/mp4 | A/B toggle can't play the prior cut |
| R3 | GET /takes/{n}/video for a pruned/missing take | 404 plain message | Player error instead of a clean state |
| R4 | POST /takes/{n}/restore | 200; project files match the take; response lists takes | Restore silently partial |
| R5 | POST restore during an active run | 409 | Restore races a run writing the same files |
| R6 | POST restore of a pruned take | 409 with the prune explanation | Film-less restore breaks project coherence |
