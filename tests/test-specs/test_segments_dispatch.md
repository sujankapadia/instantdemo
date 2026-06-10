# test_segments_dispatch.py Spec

Source: `src/instantdemo/server/routes/segments.py` (`_generate_project_audio` — M3)
Test: `tests/test_segments_dispatch.py`

## Methods not tested (and why)

| Method | Reason |
|---|---|
| `_do_re_render_audio` / `_do_delete_segment` end-to-end | Need a real demo.mp4 + ffmpeg remux; covered by scripts/smoke_segment_edit.py |

## _generate_project_audio dispatch

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| D1 | No tts.json (legacy project) | Dispatches pocket-tts / alba (monkeypatched provider fn receives voice "alba", ref None) | Legacy re-renders crash or pick a different voice than full renders — same edit, two voices |
| D2 | tts.json pocket-tts/marius + existing ref_wav | Provider fn receives voice "marius" and the RESOLVED absolute ref path | Cloned brand voice silently dropped on segment edits — the #59 core bug recreated |
| D3 | tts.json with pronunciations | Provider fn receives RESPELLED narration; caller's segments keep display text | Segment edits bypass the speech transform — re-rendered audio mispronounces what full renders fix |
| D4 | Hand-written kokoro tts.json (CLI persona) | generate_audio_kokoro called with config voice | Non-default providers break in the GUI even when configured deliberately |
| D5 | Provider fn raises SystemExit (import failure) | HTTPException 503 with install-or-switch guidance | sys.exit(1) kills the server worker instead of returning an actionable error |
