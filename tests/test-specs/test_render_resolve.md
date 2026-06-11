# test_render_resolve.py Spec

Source: `src/instantdemo/render.py` (`_resolve_tts`, `ResolvedTTS` — M3)
Test: `tests/test_render_resolve.py`

## Methods not tested (and why)

| Method | Reason |
|---|---|
| `generate_audio()` dispatcher | Dispatch correctness covered by the segments-route dispatch tests (monkeypatched providers); provider fns themselves are live-TTS, smoke territory |

## _resolve_tts precedence (flag > tts.json > defaults)

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| T1 | No flags, no config | pocket-tts / alba / no ref | Fresh projects get the wrong voice or crash |
| T2 | No flags, config (pocket-tts/marius + ref_wav on disk) | provider/voice from config; ref resolved absolute | tts.json silently ignored — the whole M3 premise broken |
| T3 | Explicit --tts kokoro over a pocket-tts config | provider kokoro; voice falls to af_heart (NOT the config's pocket voice name) | Kokoro asked to load voice "alba" — crash or garbage |
| T4 | --pocket-voice flag over config voice | Flag wins | CLI overrides don't override |
| T5 | --pocket-ref flag over config ref_wav | Flag path wins | Can't A/B a new reference from the CLI |
| T6 | Config with dangling ref_wav | ref None (stock voice fallback) | Deleted WAV bricks every render |
| T7 | Pronunciations always flow from config | resolved.pronunciations == config's regardless of provider flags | Respellings vanish when overriding the provider |
