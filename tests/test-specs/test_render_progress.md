# test_render_progress.py Spec

Source: `src/instantdemo/phases/render.py` (the thread-safe progress
emitter — M8/#85 item 1) + `src/instantdemo/render.py` (on_progress
threading through main / render_section_main / generate_audio /
record loops)
Test: `tests/test_render_progress.py`

## Why

The renderer is deterministic (segment count and slot durations known
before recording) but silent for minutes. Phase 6 builds an
`on_progress(stage, current, total)` callback that marshals
`{"type": "render_progress", "phase": 6, "stage": "narrating"|
"recording", "current": k, "total": N}` onto the asyncio loop via
`loop.call_soon_threadsafe` — the SSE queue's put_nowait is NOT
thread-safe from the executor thread.

## Methods not tested (and why)

| Method | Reason |
|---|---|
| `record_browser_video` / `record_section_video` loops | Need live Playwright; the callback call sites are one line each, gated live |
| Real TTS providers | Live-TTS smoke territory; the dispatcher pass-through and a loop-shape fake cover the contract |

## Rows

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| RP1 | The phase-6 emitter invoked from a worker thread (real event loop, run_in_executor) | The exact event dict lands on the loop-side queue; no cross-thread queue mutation | Worker-thread put_nowait corrupts the asyncio queue — Heisenbug SSE drops |
| RP2 | context.event_emitter is None (CLI) | _invoke_renderer receives on_progress=None; renderer paths accept None without emitting | CLI renders crash or demand a GUI-only callback |
| RP3 | _invoke_renderer full-render path (render_main monkeypatched) | The same callback object arrives as the on_progress kwarg | Progress silently dropped on full records |
| RP4 | _invoke_renderer section path (_section_render_plan stubbed, render_section_main monkeypatched) | Callback threaded through | Progress silently dropped on chapter splices |
| RP5 | generate_audio dispatcher (provider fn monkeypatched) | Provider receives on_progress | The narrating half never reports |
| RP6 | A provider-shaped loop fake calling on_progress per segment | ("narrating", 1..N, N) in order | Counts skip or misorder — the header lies |
