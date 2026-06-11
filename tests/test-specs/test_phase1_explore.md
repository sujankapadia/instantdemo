# test_phase1_explore.py Spec

Source: `src/instantdemo/phases/analyze.py`
Test: `tests/test_phase1_explore.py`

## Methods not tested (and why)

| Method | Reason |
|---|---|
| `run()` | Orchestration over the SDK client; covered by scripts/smoke_phase1_explore.py (live) |
| `_watch_screenshots()` | Thin async loop over the pure `new_screenshots` helper, which is tested |
| `exploration_dir()` / `_screenshot_event()` | One-line path/dict builders |

## _validate_payload()

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| PV1 | Well-formed payload (app_model, proposal with goal, screens, warnings; no `length` field since 2026-06-11 — DESIGN.md principle 11) | No problems | Valid exploration rejected — every Phase 1 run fails |
| PV2 | Empty/missing app_model | Problem naming app_model | Empty app model flows to Phase 2, which plans from nothing |
| PV3 | Missing proposed_intent.goal | Problem naming goal | Confirmation card renders with an empty goal — the product's centerpiece blank |
| PV4 | focus as a string instead of list | Problem naming the field | Malformed intent crashes IntentEditor / intent.json round-trip |
| PV5 | screens entry without name; screenshot with path separators | Two problems | Path-traversal-ish screenshot refs reach the exploration file endpoint |
| PV6 | Missing screens/warnings entirely | No problems (optional) | Overly strict validator rejects minimal-but-valid output, burning retries |
| PV7 | exp_dir given; screens reference a PNG that exists on disk | No problems | Valid screenshot-laden output rejected, retry loop burns money |
| PV8 | exp_dir given; screens present but NO referenced PNG exists | Problem instructing the agent to capture and re-emit | Agent skips screenshots (observed in the first live gate) — filmstrip and confirm card ship empty |
| PV9 | exp_dir given; one reference exists, another doesn't | Problem naming the missing file | Hallucinated screenshot refs 404 in the GUI filmstrip |

## _normalized_proposal()

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| NP1 | Proposal with nulls and missing list fields | All Intent dataclass keys present; lists default empty | GUI IntentEditor receives undefined fields and renders broken controls |

## _render_view()

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| RV1 (proposal dicts carry no `length` key since 2026-06-11) | User goal present in context | ANSWER block parses via checkpoints.parse_answer_block; flow == user goal (not the proposal) | CLI/narrate fallback chain breaks; user's stated goal silently replaced by the agent's |
| RV2 | No user goal | flow falls back to proposal goal | Empty flow line gives Phase 2 nothing on legacy CLI path |
| RV3 | Payload with screens + warnings | View contains screen bullet with route + screenshot ref, and warnings section | GUI artifact view loses the exploration evidence humans review |

## new_screenshots()

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| NS1 | Empty/missing dir | Returns [] | Watcher crashes before the agent writes anything |
| NS2 | Two new PNGs, one already seen | Returns only the new ones, sorted; seen updated | Duplicate SSE events spam the filmstrip; or new shots never emitted |
| NS3 | Non-PNG and unsafe filenames in dir | Ignored | Arbitrary files leak into SSE events and the exploration endpoint |
