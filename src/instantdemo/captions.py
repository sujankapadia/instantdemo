"""SRT captions (M6): generated from DISPLAY narration + the timing
rows, regenerated at every timing write so demo.srt is always in
sync with demo.mp4.

Display text, never speech text: pronunciation respellings (M3)
apply only to the synthesized audio — captions show the words as
written. Silent segments produce no cue. The M5b timing fixes made
the rows frame-true, which is what makes these captions sit on the
words instead of drifting.
"""

from __future__ import annotations

from pathlib import Path

SRT_FILENAME = "demo.srt"


def _timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    ms = round(seconds * 1000)
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def srt_text(segments: list[dict], rows: list[dict]) -> str:
    """One cue per non-silent segment, renumbered from 1. `segments`
    carry display narration; `rows` carry start_s/end_s (index-
    aligned with segments). Pure function (unit-tested)."""
    cues: list[str] = []
    number = 1
    for seg, row in zip(segments, rows):
        narration = (seg.get("narration") or "").strip()
        if not narration:
            continue
        cues.append(
            f"{number}\n"
            f"{_timestamp(row['start_s'])} --> {_timestamp(row['end_s'])}\n"
            f"{narration}\n"
        )
        number += 1
    return "\n".join(cues) + ("\n" if cues else "")


def write_srt(project: Path, segments: list[dict], rows: list[dict]) -> Path:
    """Write <project>/demo.srt next to demo.mp4."""
    path = project / SRT_FILENAME
    path.write_text(srt_text(segments, rows))
    return path
