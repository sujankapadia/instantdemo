# test_tts_config.py Spec

Source: `src/instantdemo/tts_config.py` (M3, issue #59)
Test: `tests/test_tts_config.py`

## Methods not tested (and why)

| Method | Reason |
|---|---|
| `pocket_stock_voices()` | Thin try/import wrapper over a vendored list; the fallback IS the snapshot constant |
| `tts_path()` | One-line path join |

## load / save / defaults

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| C1 | save → load round-trip with ref_wav + pronunciations + consent | All fields survive | Voice config silently loses the cloned reference or respellings between sessions |
| C2 | No tts.json | load → None; load_or_default → pocket-tts/alba, no ref, empty pronunciations | Legacy projects crash or get an undefined voice |
| C3 | Malformed JSON / non-dict JSON | load → None (no raise) | A hand-edited typo bricks every render and the voice dialog |
| C4 | Entries missing match or say are dropped on load | Only complete entries survive | Half-authored rows from a crashed save corrupt the speech transform |

## resolve_ref_wav

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| R1 | ref_wav set and file exists | Absolute resolved path returned | Cloned voice never used despite being configured |
| R2 | ref_wav set but file missing (dangling) | None (no raise) | A deleted reference WAV crashes renders instead of falling back to stock voice |
| R3 | ref_wav unset | None | Stock-voice projects try to clone from nothing |

## apply_pronunciations (the speech-text transform)

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| P1 | Whole-word match | "Evernote is great" → "Ever note is great" | The entire pronunciation feature does nothing |
| P2 | NO partial-word hit | "Evernotes" untouched by an "Evernote" entry | Respelling bleeds into unrelated words mid-sentence |
| P3 | Case-sensitive | "evernote" untouched by an "Evernote" entry | Lowercase variants get rewritten when the user only vetted the cased form |
| P4 | Multi-entry, list order | Both entries applied; earlier entry's output visible to later | Order-dependent authoring breaks unpredictably |
| P5 | Multi-word match | "Claude Code" → respelled as one unit | Product names with spaces can't be fixed |
| P6 | Empty text / empty entries | Returned unchanged, no raise | Silent segments crash synthesis |

## speech_segments (the display-text guarantee)

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| S1 | Transform applies to copies | Returned segments have respelled narration; ORIGINAL list objects unmutated (the most important assertion in M3) | Respellings leak into demo-script.json / storyboard / captions — display text corrupted everywhere downstream |
| S2 | No entries | Same list returned (fast path), originals identical | Pointless copying churn; behavioral drift between paths |
