# test_captions.py Spec

Source: `src/instantdemo/captions.py` (M6) + the timing-write hooks
Test: `tests/test_captions.py`

## Methods not tested (and why)

| Method | Reason |
|---|---|
| `write_srt` file I/O | One write_text call; the hook tests below exercise it through real callers |

## srt_text()

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| CP1 | Three segments, middle one silent | Two cues numbered 1,2 (renumbered — no gap); silent segment absent | Players show empty cues or numbering breaks strict parsers |
| CP2 | Timestamp formatting | 0 → 00:00:00,000; 3661.5 → 01:01:01,500; comma millis (SRT, not VTT dots) | Captions rejected by players/platforms |
| CP3 | Display text verbatim | Cue text == narration exactly (no speech respellings — that's the M3 split) | Captions show "ee-nex" instead of "ENEX" |
| CP4 | Empty segment list | Returns "" (no trailing junk) | Zero-scene edge writes a corrupt file |

## Hooks (demo.srt rides every timing write)

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| CP5 | _write_segment_timing called | demo.srt exists next to the project's demo.mp4, cues match rows | Full render / re-voice / delete leave stale captions — desync the user can't see until a platform shows it |
| CP6 | takes.SNAPSHOT_FILES includes demo.srt | snapshot copies it; restore brings it back | A restored take's captions describe a different film |
| CP7 | GET /api/project/download | A zip containing demo.mp4 + demo.srt (srt omitted when absent; 404 with no film) | The one-click deliverable ships broken or half-empty |
