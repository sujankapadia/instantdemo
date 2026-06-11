# test_voice_routes.py Spec

App: `instantdemo.server.app` (voice router, M3 #59)
Test: `tests/test_voice_routes.py`

## Methods not tested (and why)

| Method | Reason |
|---|---|
| `_synthesize_preview` real synthesis | Loads the pocket model (~3-5s + network on first run); preview tests monkeypatch it. Real synthesis covered by L5 sign-off |
| `_peak_dbfs` / `_probe_duration_s` directly | Exercised through the upload tests with real ffmpeg-generated fixtures (lavfi sine / anullsrc plain-string sources) |

## GET /api/project/voice

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| V1 | No tts.json | persisted=false, config pocket-tts/alba, 26 voices listed, pocket_installed bool | Dialog can't render its initial state on fresh projects |
| V2 | tts.json with voice + ref on disk | persisted=true, ref_exists=true, config round-trips | Dialog shows stale/default state over a configured project |

## PUT /api/project/voice

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| V3 | Update voice to a known stock name | Persisted to tts.json; response reflects it | Voice picker saves nothing |
| V4 | Unknown voice name | 422 | Typos brick the next render |
| V5 | Update pronunciations (incl. a blank row) | Blank rows dropped; entries persisted | Half-empty rows corrupt the speech transform |
| V6 | Active run in progress | 409 | Config write races a running render |

## POST /api/project/voice/reference

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| V7 | consent=false | 422 mentioning consent; nothing stored | Cloning without affirmation — the #59 legal requirement |
| V8 | 1s clip (ffmpeg sine fixture) | 422 "too short"; nothing stored | Useless references accepted, cloning quality garbage with no explanation |
| V9 | Silent clip (anullsrc fixture) | 422 "silent"; nothing stored | The bake-off's exact failure mode (wrong mic) accepted silently |
| V10 | Valid 5s sine clip uploaded as m4a-ish input | 200; .instantdemo/voice-reference.wav exists as WAV; tts.json gains ref_wav + consent.given=true | Upload "succeeds" but render finds no reference |
| V11 | DELETE after V10 | ref gone from disk; config ref_wav + consent cleared | Deleted voice still haunts renders |

## POST /api/project/voice/preview

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| V12 | Default preview (synth monkeypatched) | 200 audio/wav; synth received config voice | ▶ buttons dead |
| V13 | Preview with explicit voice + pronunciation rows | Synth receives RESPELLED text and the requested voice | Listen-check lies — verifies different text than renders use |
| V14 | use_reference=true with no reference | 404 | Confusing 500 instead of "upload first" |
