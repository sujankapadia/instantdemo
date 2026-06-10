#!/usr/bin/env python3
"""Bake-off worker: Pocket TTS (Kyutai). Runs in an isolated uv env:

    uv run --no-project --python 3.11 --with pocket-tts --with soundfile \
        worker_pocket_tts.py ...

Stock voice and cloning use the same API: get_state_for_audio_prompt
takes either a predefined voice name or a local WAV path. CPU is the
recommended device (README: GPU shows no speedup).

The HF weights repo (kyutai/pocket-tts) is gated behind a click-through;
on 401/403 we print the unlock instructions and exit 3.
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

STOCK_VOICE = "alba"


def main() -> int:
    args = build_arg_parser(__doc__ or "pocket-tts bake-off worker").parse_args()
    if args.variant == "clone" and not args.ref_wav:
        print("clone variant requires --ref-wav", file=sys.stderr)
        return 2

    import soundfile as sf

    stats = StatsCollector("pocket-tts", args.variant)
    stats.device = "cpu"
    try:
        import pocket_tts
        from pocket_tts import TTSModel

        stats.versions = {
            "pocket-tts": getattr(pocket_tts, "__version__", "unknown")
        }
        with timed() as t:
            model = TTSModel.load_model()
    except Exception as e:
        msg = str(e)
        if "401" in msg or "403" in msg or "gated" in msg.lower():
            print(
                "Pocket TTS weights are gated. Accept the conditions at "
                "https://huggingface.co/kyutai/pocket-tts then "
                "`huggingface-cli login` (or set HF_TOKEN) and re-run.",
                file=sys.stderr,
            )
            return 3
        raise
    stats.model_load_s = t.elapsed
    stats.sample_rate = int(model.sample_rate)

    prompt = (
        str(args.ref_wav) if args.variant == "clone" else STOCK_VOICE
    )
    print(f"  voice prompt: {prompt}", flush=True)
    voice_state = model.get_state_for_audio_prompt(prompt)

    segments = load_narrations(args.narrations)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for seg in segments:
        out_path = args.out_dir / f"segment_{seg['index']:02d}.wav"
        print(f"  segment {seg['index']}: {seg['text'][:50]}...", flush=True)
        with timed() as t:
            audio = model.generate_audio(voice_state, seg["text"])
            sf.write(
                str(out_path),
                audio.numpy() if hasattr(audio, "numpy") else audio,
                int(model.sample_rate),
            )
        stats.add_segment(seg["index"], seg["text"], t.elapsed, out_path)

    stats.write(args.out_dir)
    print(f"[pocket-tts] done: {len(segments)} segments -> {args.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
