#!/usr/bin/env python3
"""Bake-off worker: Chatterbox (Resemble AI). Runs in an isolated uv env:

    uv run --no-project --python 3.11 --with chatterbox-tts --with soundfile \
        worker_chatterbox.py ...

Mac notes (resemble-ai/chatterbox#85): checkpoints were serialized with
CUDA device refs, so torch.load must be patched to force map_location.
MPS sometimes fails with placeholder-storage errors; we try MPS then
fall back to CPU and record which device actually ran. Expect the
slowest synthesis of the bake-off on CPU. Output is Perth-watermarked
by design.
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


def _patch_torch_load(device: str) -> None:
    """Force map_location so CUDA-serialized checkpoints load on Mac."""
    import torch

    original = torch.load

    def patched(*a, **kw):
        kw.setdefault("map_location", torch.device(device))
        return original(*a, **kw)

    torch.load = patched


def _load_model(stats: StatsCollector):
    import torch

    candidates = []
    if torch.backends.mps.is_available():
        candidates.append("mps")
    candidates.append("cpu")

    from chatterbox.tts import ChatterboxTTS

    last_err: Exception | None = None
    for device in candidates:
        try:
            _patch_torch_load(device)
            with timed() as t:
                model = ChatterboxTTS.from_pretrained(device=device)
            stats.device = device
            stats.model_load_s = t.elapsed
            return model
        except Exception as e:  # noqa: BLE001 — try the next device
            stats.note(f"load on {device} failed: {str(e)[:200]}")
            last_err = e
    raise RuntimeError(f"all devices failed: {last_err}")


def main() -> int:
    args = build_arg_parser(__doc__ or "chatterbox bake-off worker").parse_args()
    if args.variant == "clone" and not args.ref_wav:
        print("clone variant requires --ref-wav", file=sys.stderr)
        return 2

    import soundfile as sf

    stats = StatsCollector("chatterbox", args.variant)
    try:
        import chatterbox

        stats.versions = {
            "chatterbox-tts": getattr(chatterbox, "__version__", "unknown")
        }
    except Exception:
        pass

    model = _load_model(stats)
    stats.sample_rate = int(model.sr)

    segments = load_narrations(args.narrations)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for seg in segments:
        out_path = args.out_dir / f"segment_{seg['index']:02d}.wav"
        print(f"  segment {seg['index']}: {seg['text'][:50]}...", flush=True)
        with timed() as t:
            if args.variant == "clone":
                wav = model.generate(
                    seg["text"], audio_prompt_path=str(args.ref_wav)
                )
            else:
                wav = model.generate(seg["text"])
            # generate() returns a torch tensor, possibly (1, N)
            audio = wav.squeeze().cpu().numpy()
            sf.write(str(out_path), audio, int(model.sr))
        stats.add_segment(seg["index"], seg["text"], t.elapsed, out_path)

    stats.write(args.out_dir)
    print(f"[chatterbox] done: {len(segments)} segments -> {args.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
