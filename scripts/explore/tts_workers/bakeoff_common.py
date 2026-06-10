"""Shared protocol helpers for TTS bake-off workers.

STDLIB-ONLY by design: workers run in isolated uv environments that
have their TTS package + soundfile and nothing else from this repo.
Each worker imports this module as a sibling file (the worker's own
directory is on sys.path), so it must not import torch, numpy, or
anything from instantdemo.

Protocol (every worker):

    worker_X.py --narrations narrations.json --out-dir DIR \
                --variant stock|clone [--ref-wav P --ref-text-file P] \
                [--device auto|cpu|mps]

The worker writes segment_NN.wav files (NN = zero-padded original
fixture index) plus a stats.json, and exits non-zero with a stderr
message on failure.
"""

from __future__ import annotations

import argparse
import json
import time
import wave
from pathlib import Path


def build_arg_parser(description: str) -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument("--narrations", required=True, type=Path,
                    help="narrations.json from the orchestrator")
    ap.add_argument("--out-dir", required=True, type=Path,
                    help="variant output directory (created if missing)")
    ap.add_argument("--variant", required=True, choices=["stock", "clone"])
    ap.add_argument("--ref-wav", type=Path, default=None,
                    help="reference WAV for clone variants")
    ap.add_argument("--ref-text-file", type=Path, default=None,
                    help="transcript of the reference WAV (some models need it)")
    ap.add_argument("--device", choices=["auto", "cpu", "mps"], default="auto")
    return ap


def load_narrations(path: Path) -> list[dict]:
    """Return [{"index": int, "text": str}, ...] — already filtered to
    non-empty narrations by the orchestrator."""
    data = json.loads(path.read_text())
    return data["segments"]


def wav_duration_s(path: Path) -> float:
    """Duration of a PCM WAV via the stdlib wave module."""
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


class StatsCollector:
    """Accumulates timing/size facts and writes the stats.json the
    orchestrator consumes. Wall clock starts at construction."""

    def __init__(self, provider: str, variant: str) -> None:
        self.provider = provider
        self.variant = variant
        self.device: str | None = None
        self.sample_rate: int | None = None
        self.model_load_s: float | None = None
        self.segments: list[dict] = []
        self.notes: list[str] = []
        self.versions: dict[str, str] = {}
        self._wall_start = time.monotonic()

    def note(self, message: str) -> None:
        self.notes.append(message)
        print(f"  [note] {message}", flush=True)

    def add_segment(
        self, index: int, text: str, synth_s: float, wav_path: Path
    ) -> None:
        audio_s = wav_duration_s(wav_path)
        self.segments.append(
            {
                "index": index,
                "chars": len(text),
                "synth_s": round(synth_s, 3),
                "audio_s": round(audio_s, 3),
                "rtf": round(synth_s / audio_s, 3) if audio_s > 0 else None,
                "bytes": wav_path.stat().st_size,
                "file": wav_path.name,
            }
        )

    def write(self, out_dir: Path) -> Path:
        total_synth = sum(s["synth_s"] for s in self.segments)
        total_audio = sum(s["audio_s"] for s in self.segments)
        stats = {
            "provider": self.provider,
            "variant": self.variant,
            "device": self.device,
            "sample_rate": self.sample_rate,
            "model_load_s": (
                round(self.model_load_s, 3)
                if self.model_load_s is not None else None
            ),
            "segments": self.segments,
            "total_synth_s": round(total_synth, 3),
            "total_audio_s": round(total_audio, 3),
            "overall_rtf": (
                round(total_synth / total_audio, 3) if total_audio > 0 else None
            ),
            "total_wall_s": round(time.monotonic() - self._wall_start, 3),
            "versions": self.versions,
            "notes": self.notes,
        }
        out_path = out_dir / "stats.json"
        out_path.write_text(json.dumps(stats, indent=2))
        return out_path


class timed:
    """Context manager: `with timed() as t: ...; t.elapsed`."""

    def __enter__(self) -> "timed":
        self._start = time.monotonic()
        self.elapsed = 0.0
        return self

    def __exit__(self, *_exc) -> None:
        self.elapsed = time.monotonic() - self._start
