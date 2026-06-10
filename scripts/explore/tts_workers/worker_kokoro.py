#!/usr/bin/env python3
"""Bake-off worker: Kokoro (the current InstantDemo default voice).

Runs in the repo's main environment (kokoro + soundfile already
installed). Two modes:

1. Normal protocol (see bakeoff_common): synthesize narration segments
   with the stock af_heart voice. `--variant clone` is rejected —
   Kokoro can't clone.
2. `--make-reference --text-file P --out-wav P`: render the reference
   paragraph to a single WAV. Used by the orchestrator to produce the
   synthetic cloning reference the other models try to mimic.

Mirrors src/instantdemo/render.py::generate_audio_kokoro with one
deliberate divergence: ALL pipeline chunks are concatenated, where
render.py `break`s after the first. (If KPipeline ever yields more
than one chunk for demo-length narration, render.py truncates audio —
this worker prints a loud note when it sees multi-chunk output so we
learn whether that latent bug is real.)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from bakeoff_common import (  # noqa: E402
    StatsCollector,
    build_arg_parser,
    load_narrations,
    timed,
)

VOICE = "af_heart"
SPEED = 1.0
SAMPLE_RATE = 24000


def _load_pipeline():
    from kokoro import KPipeline

    return KPipeline(lang_code=VOICE[0])


def _synthesize(pipeline, text: str):
    """Run Kokoro over `text`, concatenating all yielded chunks."""
    import numpy as np

    chunks = [audio for _gs, _ps, audio in pipeline(text, voice=VOICE, speed=SPEED)]
    if len(chunks) > 1:
        print(
            f"  [note] KPipeline yielded {len(chunks)} chunks for one "
            "narration — render.py's break-after-first would truncate this!",
            flush=True,
        )
    return np.concatenate(chunks) if len(chunks) > 1 else chunks[0], len(chunks)


def make_reference(text_file: Path, out_wav: Path) -> int:
    import soundfile as sf

    text = text_file.read_text().strip()
    print(f"[kokoro] rendering reference ({len(text)} chars) -> {out_wav}")
    pipeline = _load_pipeline()
    audio, _n = _synthesize(pipeline, text)
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out_wav), audio, SAMPLE_RATE)
    print(f"[kokoro] reference written ({out_wav.stat().st_size} bytes)")
    return 0


def main() -> int:
    # --make-reference mode pre-empts the standard protocol.
    if "--make-reference" in sys.argv:
        import argparse

        ap = argparse.ArgumentParser()
        ap.add_argument("--make-reference", action="store_true")
        ap.add_argument("--text-file", required=True, type=Path)
        ap.add_argument("--out-wav", required=True, type=Path)
        args = ap.parse_args()
        return make_reference(args.text_file, args.out_wav)

    args = build_arg_parser(__doc__ or "kokoro bake-off worker").parse_args()
    if args.variant != "stock":
        print("kokoro worker supports only --variant stock", file=sys.stderr)
        return 2

    import kokoro
    import soundfile as sf

    segments = load_narrations(args.narrations)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    stats = StatsCollector("kokoro", args.variant)
    stats.device = "cpu"
    stats.sample_rate = SAMPLE_RATE
    stats.versions = {"kokoro": getattr(kokoro, "__version__", "unknown")}

    with timed() as t:
        pipeline = _load_pipeline()
    stats.model_load_s = t.elapsed

    for seg in segments:
        out_path = args.out_dir / f"segment_{seg['index']:02d}.wav"
        print(f"  segment {seg['index']}: {seg['text'][:50]}...", flush=True)
        with timed() as t:
            audio, n_chunks = _synthesize(pipeline, seg["text"])
            sf.write(str(out_path), audio, SAMPLE_RATE)
        if n_chunks > 1:
            stats.note(
                f"segment {seg['index']}: {n_chunks} kokoro chunks "
                "(render.py would truncate)"
            )
        stats.add_segment(seg["index"], seg["text"], t.elapsed, out_path)

    stats.write(args.out_dir)
    print(f"[kokoro] done: {len(segments)} segments -> {args.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
