#!/usr/bin/env python3
"""Bake-off worker: OmniVoice (k2-fsa). Runs in an isolated uv env:

    uv run --no-project --python 3.11 --with torch==2.8.0 \
        --with torchaudio==2.8.0 --with omnivoice --with soundfile \
        worker_omnivoice.py ...

Cloning requires BOTH the reference audio and its transcript
(--ref-text-file) — the orchestrator passes the fixed reference
paragraph, which every reference recording reads. MPS is explicitly
supported per the HF card; falls back to CPU and records the device
actually used.
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

MODEL_ID = "k2-fsa/OmniVoice"
SAMPLE_RATE = 24000


def _load_model(stats: StatsCollector):
    import torch
    from omnivoice import OmniVoice

    candidates = []
    if torch.backends.mps.is_available():
        candidates.append("mps")
    candidates.append("cpu")

    last_err: Exception | None = None
    for device in candidates:
        try:
            with timed() as t:
                model = OmniVoice.from_pretrained(MODEL_ID, device_map=device)
            stats.device = device
            stats.model_load_s = t.elapsed
            return model
        except Exception as e:  # noqa: BLE001 — try the next device
            stats.note(f"load on {device} failed: {str(e)[:200]}")
            last_err = e
    raise RuntimeError(f"all devices failed: {last_err}")


def main() -> int:
    args = build_arg_parser(__doc__ or "omnivoice bake-off worker").parse_args()
    if args.variant == "clone" and not (args.ref_wav and args.ref_text_file):
        print(
            "clone variant requires --ref-wav and --ref-text-file",
            file=sys.stderr,
        )
        return 2

    import numpy as np
    import soundfile as sf

    stats = StatsCollector("omnivoice", args.variant)
    try:
        import omnivoice as ov

        stats.versions = {"omnivoice": getattr(ov, "__version__", "unknown")}
    except Exception:
        pass

    model = _load_model(stats)
    stats.sample_rate = SAMPLE_RATE
    ref_text = (
        args.ref_text_file.read_text().strip()
        if args.variant == "clone" else None
    )

    segments = load_narrations(args.narrations)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for seg in segments:
        out_path = args.out_dir / f"segment_{seg['index']:02d}.wav"
        print(f"  segment {seg['index']}: {seg['text'][:50]}...", flush=True)
        with timed() as t:
            if args.variant == "clone":
                audio = model.generate(
                    text=seg["text"],
                    ref_audio=str(args.ref_wav),
                    ref_text=ref_text,
                )
            else:
                audio = model.generate(text=seg["text"])
            # returns list of np.ndarray (T,) per the model card
            arr = audio[0] if isinstance(audio, (list, tuple)) else audio
            arr = np.asarray(arr).squeeze()
            sf.write(str(out_path), arr, SAMPLE_RATE)
        stats.add_segment(seg["index"], seg["text"], t.elapsed, out_path)

    stats.write(args.out_dir)
    print(f"[omnivoice] done: {len(segments)} segments -> {args.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
