#!/usr/bin/env python3
"""TTS bake-off: render one demo's narration through multiple local TTS
models — stock voices and CLONED voices — into a side-by-side HTML
listening page.

Purpose: decide whether InstantDemo can offer a local "brand voice"
(cloning) tier. See docs/local-tts-models.md for the model landscape
and PRODUCT_DIRECTION.md for why this matters.

Providers (each runs in an isolated uv environment so their
conflicting torch pins never meet; only Kokoro uses the repo env):

    kokoro      baseline af_heart (today's default demo voice)
    pocket-tts  Kyutai, MIT, CPU-only, 5s cloning
    chatterbox  Resemble AI, MIT (slow on Mac: CPU fallback)
    omnivoice   k2-fsa, Apache 2.0 (clone needs reference transcript)

Cloning references: a synthetic one (Kokoro af_heart reading the
REFERENCE_PARAGRAPH — clones mimicking it is an objective fidelity
test against the baseline column) and optionally your own voice
reading the SAME paragraph (--user-ref path/to/recording, any format;
or --record to capture via ffmpeg/avfoundation).

Usage:
    python scripts/explore/tts_bakeoff.py                      # synthetic refs only
    python scripts/explore/tts_bakeoff.py --user-ref me.m4a    # + your voice
    python scripts/explore/tts_bakeoff.py --providers pocket-tts --skip-existing
    python scripts/explore/tts_bakeoff.py --rebuild-html       # regen page only

First run downloads model weights (~6 GB total across providers) into
the shared HuggingFace cache; budget time accordingly or run one
provider at a time. Pocket TTS's HF repo is gated: accept the terms at
huggingface.co/kyutai/pocket-tts and `huggingface-cli login` first.

Output: scripts/explore/out/tts-bakeoff/<run-name>/index.html
(self-contained — relative links; open via file:// or move the dir).
"""

from __future__ import annotations

import argparse
import html
import json
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKERS_DIR = Path(__file__).resolve().parent / "tts_workers"
DEFAULT_SCRIPT = (
    REPO_ROOT
    / "fixtures/source-free-evernote-jailed-2026-06-09/demo-script.json"
)
DEFAULT_OUT_ROOT = Path(__file__).resolve().parent / "out" / "tts-bakeoff"

# Read aloud by every cloning reference (synthetic and user). Also
# serves as OmniVoice's required reference transcript. ~33 words,
# roughly 10-12 seconds spoken.
REFERENCE_PARAGRAPH = (
    "Welcome to this product demo. Over the next minute, we'll explore "
    "the main screens together, click through a real workflow, and see "
    "exactly how everything fits, one step at a time."
)

UV = "uv"
PYTHON_VERSION = "3.11"

# provider -> (worker filename, uv --with deps or None for repo env,
#              supports_clone)
PROVIDERS: dict[str, tuple[str, list[str] | None, bool]] = {
    "kokoro": ("worker_kokoro.py", None, False),
    "pocket-tts": (
        "worker_pocket_tts.py",
        ["pocket-tts", "soundfile"],
        True,
    ),
    "chatterbox": (
        "worker_chatterbox.py",
        ["chatterbox-tts", "soundfile"],
        True,
    ),
    "omnivoice": (
        "worker_omnivoice.py",
        ["torch==2.8.0", "torchaudio==2.8.0", "omnivoice", "soundfile"],
        True,
    ),
}

VARIANT_LABELS = {
    "stock": "stock",
    "clone-synth": "clone of af_heart",
    "clone-user": "clone of your voice",
}


def load_segments(script_path: Path) -> tuple[list[dict], list[dict]]:
    """Return (all_segments, nonempty) where nonempty is
    [{"index": i, "text": narration}, ...] with original indices."""
    script = json.loads(script_path.read_text())
    all_segments = script["segments"]
    nonempty = [
        {"index": i, "text": seg.get("narration", "").strip()}
        for i, seg in enumerate(all_segments)
        if seg.get("narration", "").strip()
    ]
    return all_segments, nonempty


def ensure_synthetic_ref(refs_dir: Path) -> Path:
    ref = refs_dir / "reference_synthetic.wav"
    if ref.exists():
        return ref
    refs_dir.mkdir(parents=True, exist_ok=True)
    text_file = refs_dir / "reference_paragraph.txt"
    text_file.write_text(REFERENCE_PARAGRAPH)
    print("[bakeoff] generating synthetic reference (kokoro af_heart)...")
    subprocess.run(
        [
            sys.executable,
            str(WORKERS_DIR / "worker_kokoro.py"),
            "--make-reference",
            "--text-file", str(text_file),
            "--out-wav", str(ref),
        ],
        check=True,
    )
    return ref


def normalize_user_ref(src: Path, refs_dir: Path) -> Path:
    """Any input format -> mono 24 kHz 16-bit WAV via ffmpeg."""
    refs_dir.mkdir(parents=True, exist_ok=True)
    dst = refs_dir / "reference_user.wav"
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(src),
            "-ac", "1", "-ar", "24000", "-sample_fmt", "s16",
            str(dst),
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed on {src}: {result.stderr[-500:]}")
    return dst


def record_user_ref(refs_dir: Path, seconds: int = 12, device: str = "0") -> Path:
    """Capture the user's voice via ffmpeg/avfoundation.

    `device` is an avfoundation audio input index OR device name — list
    with `ffmpeg -f avfoundation -list_devices true -i ""`. Prefer the
    NAME ("MacBook Pro Microphone"): indices reshuffle whenever devices
    connect/disconnect, and index 0 is often a silent virtual device
    (e.g. "Microsoft Teams Audio"). QuickTime / Voice Memos +
    --user-ref remains the most reliable path.
    """
    refs_dir.mkdir(parents=True, exist_ok=True)
    raw = refs_dir / "reference_user_raw.wav"
    print("\nRead this paragraph aloud when recording starts:\n")
    print(f"    {REFERENCE_PARAGRAPH}\n")
    for n in (3, 2, 1):
        print(f"  recording in {n}...")
        time.sleep(1)
    print(f"  RECORDING ({seconds}s) — speak now")
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-f", "avfoundation", "-i", f":{device}",
            "-t", str(seconds), str(raw),
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "ffmpeg recording failed (mic permissions? try QuickTime + "
            f"--user-ref instead): {result.stderr[-500:]}"
        )
    print("  done.")
    return normalize_user_ref(raw, refs_dir)


def worker_command(provider: str, worker_args: list[str]) -> list[str]:
    worker_file, uv_deps, _ = PROVIDERS[provider]
    worker_path = str(WORKERS_DIR / worker_file)
    if uv_deps is None:
        return [sys.executable, worker_path, *worker_args]
    cmd = [UV, "run", "--no-project", "--python", PYTHON_VERSION]
    for dep in uv_deps:
        cmd += ["--with", dep]
    return [*cmd, worker_path, *worker_args]


def run_variant(
    provider: str,
    variant: str,
    run_dir: Path,
    refs: dict[str, Path],
    timeout_s: int,
    skip_existing: bool,
) -> dict:
    """Execute one provider/variant worker; return a status record."""
    variant_dir = run_dir / f"{provider}-{variant}"
    stats_path = variant_dir / "stats.json"
    if skip_existing and stats_path.exists():
        print(f"[bakeoff] {provider}/{variant}: exists, skipping")
        return {"provider": provider, "variant": variant, "status": "ok",
                "skipped": True}

    variant_dir.mkdir(parents=True, exist_ok=True)
    worker_args = [
        "--narrations", str(run_dir / "narrations.json"),
        "--out-dir", str(variant_dir),
        "--variant", "clone" if variant.startswith("clone") else "stock",
    ]
    if variant == "clone-synth":
        worker_args += ["--ref-wav", str(refs["synthetic"])]
    elif variant == "clone-user":
        worker_args += ["--ref-wav", str(refs["user"])]
    if variant.startswith("clone"):
        worker_args += [
            "--ref-text-file", str(refs["paragraph"]),
        ]

    cmd = worker_command(provider, worker_args)
    log_path = variant_dir / "worker.log"
    print(f"[bakeoff] {provider}/{variant}: running "
          f"(log: {log_path.relative_to(run_dir.parent)})")
    started = time.monotonic()
    with open(log_path, "w") as log:
        log.write(f"$ {' '.join(cmd)}\n\n")
        log.flush()
        try:
            proc = subprocess.run(
                cmd, stdout=log, stderr=subprocess.STDOUT,
                timeout=timeout_s, cwd=str(REPO_ROOT),
            )
            rc = proc.returncode
        except subprocess.TimeoutExpired:
            log.write(f"\n[bakeoff] TIMEOUT after {timeout_s}s\n")
            rc = -1
    wall = time.monotonic() - started
    status = "ok" if rc == 0 and stats_path.exists() else "failed"
    print(f"[bakeoff] {provider}/{variant}: {status} ({wall:.0f}s)")
    return {
        "provider": provider, "variant": variant, "status": status,
        "exit_code": rc, "wall_s": round(wall, 1),
    }


def build_html(run_dir: Path, script_path: Path, user_ref: bool) -> Path:
    all_segments, _ = load_segments(script_path)
    columns: list[tuple[str, str, dict | None]] = []  # (dirname, label, stats)
    for provider in PROVIDERS:
        for variant in ("stock", "clone-synth", "clone-user"):
            d = run_dir / f"{provider}-{variant}"
            if not d.exists():
                continue
            stats = None
            sp = d / "stats.json"
            if sp.exists():
                stats = json.loads(sp.read_text())
            columns.append(
                (d.name, f"{provider}<br><small>{VARIANT_LABELS[variant]}</small>",
                 stats)
            )

    def cell(dirname: str, stats: dict | None, idx: int) -> str:
        f = f"{dirname}/segment_{idx:02d}.wav"
        if stats is None:
            return ('<td class="err">failed — see '
                    f'<a href="{dirname}/worker.log">log</a></td>')
        if not (run_dir / f).exists():
            return '<td class="err">missing</td>'
        return (f'<td><audio controls preload="none" class="col-{dirname}" '
                f'src="{f}"></audio></td>')

    rows = []
    for i, seg in enumerate(all_segments):
        narration = seg.get("narration", "").strip()
        if not narration:
            rows.append(
                f'<tr class="empty"><td>{i}</td>'
                f'<td colspan="{len(columns) + 1}">(no narration)</td></tr>'
            )
            continue
        cells = "".join(cell(d, s, i) for d, _l, s in columns)
        rows.append(
            f"<tr><td>{i}</td><td class=\"narr\">{html.escape(narration)}</td>"
            f"{cells}</tr>"
        )

    def stat_row(label: str, fn) -> str:
        cells = "".join(
            f"<td>{fn(s) if s else '—'}</td>" for _d, _l, s in columns
        )
        return f'<tr><td colspan="2">{label}</td>{cells}</tr>'

    stats_rows = "".join([
        stat_row("model load (s)", lambda s: s.get("model_load_s")),
        stat_row("total synth (s)", lambda s: s.get("total_synth_s")),
        stat_row("overall RTF (lower=faster)", lambda s: s.get("overall_rtf")),
        stat_row("sample rate", lambda s: s.get("sample_rate")),
        stat_row("device", lambda s: s.get("device")),
        stat_row(
            "total audio bytes",
            lambda s: f"{sum(x['bytes'] for x in s.get('segments', [])):,}",
        ),
        stat_row(
            "versions",
            lambda s: "<br>".join(
                f"{k} {v}" for k, v in (s.get("versions") or {}).items()
            ) or "—",
        ),
        stat_row(
            "notes",
            lambda s: "<br>".join(map(html.escape, s.get("notes") or [])) or "—",
        ),
    ])

    headers = "".join(f"<th>{label}</th>" for _d, label, _s in columns)
    play_buttons = "".join(
        f'<th><button onclick="playColumn(\'{d}\')">▶ all</button></th>'
        for d, _l, _s in columns
    )
    user_ref_html = (
        '<p>Your-voice reference: '
        '<audio controls preload="none" src="refs/reference_user.wav"></audio></p>'
        if user_ref else
        "<p><em>No user-voice reference provided — clone-of-your-voice "
        "columns omitted. Re-run with --user-ref.</em></p>"
    )

    page = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>TTS bake-off</title>
<style>
  body {{ font-family: -apple-system, sans-serif; margin: 2rem; }}
  table {{ border-collapse: collapse; }}
  th, td {{ border: 1px solid #ddd; padding: 6px 8px; vertical-align: top;
            font-size: 13px; }}
  th {{ background: #f5f5f5; position: sticky; top: 0; }}
  td.narr {{ max-width: 260px; }}
  tr.empty td {{ color: #aaa; background: #fafafa; }}
  td.err {{ background: #fee; color: #900; }}
  audio {{ width: 220px; }}
  .stats td {{ font-size: 12px; }}
  blockquote {{ background: #f8f8f8; padding: 8px 12px; border-left: 3px solid #ccc; }}
</style></head><body>
<h1>TTS bake-off</h1>
<p>Fixture: <code>{html.escape(str(script_path))}</code> ·
   Hardware: Apple M1 Pro 32GB ·
   Generated: {time.strftime("%Y-%m-%d %H:%M")}</p>
<h2>Cloning reference</h2>
<p>Every clone column was given a ~10s sample of a voice reading this
paragraph. Judge clone columns by how close they come to their source:
the af_heart clones should sound like the kokoro baseline column; the
your-voice clones should sound like you.</p>
<blockquote>{html.escape(REFERENCE_PARAGRAPH)}</blockquote>
<p>Synthetic reference (af_heart):
   <audio controls preload="none" src="refs/reference_synthetic.wav"></audio></p>
{user_ref_html}
<h2>Segments</h2>
<table>
<tr><th>#</th><th>narration</th>{headers}</tr>
<tr><th></th><th></th>{play_buttons}</tr>
{"".join(rows)}
<tbody class="stats">
{stats_rows}
</tbody>
</table>
<p><small>Notes: native sample rates preserved (no resampling).
Chatterbox output carries a Perth neural watermark by design.
First-run timings may include model downloads — re-run with
--skip-existing for warm numbers. Sampling-based models vary between
runs.</small></p>
<script>
function playColumn(cls) {{
  const players = [...document.querySelectorAll('audio.col-' + cls)];
  let i = 0;
  const next = () => {{
    if (i >= players.length) return;
    const p = players[i++];
    p.onended = next;
    p.play();
  }};
  next();
}}
</script>
</body></html>
"""
    out = run_dir / "index.html"
    out.write_text(page)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--script", type=Path, default=DEFAULT_SCRIPT,
                    help="demo-script.json to take narrations from")
    ap.add_argument("--out", type=Path, default=None,
                    help="run directory (default: out/tts-bakeoff/<fixture>-<date>)")
    ap.add_argument("--providers", nargs="+", choices=list(PROVIDERS),
                    default=list(PROVIDERS),
                    help="subset of providers to run")
    ap.add_argument("--user-ref", type=Path, default=None,
                    help="recording of you reading the reference paragraph "
                         "(any format; normalized via ffmpeg)")
    ap.add_argument("--record", action="store_true",
                    help="record the user reference now via ffmpeg/avfoundation")
    ap.add_argument("--record-device", type=str, default="0",
                    help="avfoundation audio input index or NAME (list with "
                         "`ffmpeg -f avfoundation -list_devices true -i \"\"`); "
                         "prefer the name — indices reshuffle as devices "
                         "come and go, and index 0 is often a silent "
                         "virtual device")
    ap.add_argument("--skip-existing", action="store_true",
                    help="skip variants that already have a stats.json")
    ap.add_argument("--timeout", type=int, default=1800,
                    help="per-worker timeout in seconds (default 1800)")
    ap.add_argument("--rebuild-html", action="store_true",
                    help="only regenerate index.html from existing outputs")
    args = ap.parse_args()

    run_name = f"{args.script.parent.name}-{time.strftime('%Y-%m-%d')}"
    run_dir = args.out or (DEFAULT_OUT_ROOT / run_name)
    run_dir.mkdir(parents=True, exist_ok=True)
    refs_dir = run_dir / "refs"

    if args.rebuild_html:
        out = build_html(run_dir, args.script,
                         (refs_dir / "reference_user.wav").exists())
        print(f"[bakeoff] rebuilt {out}")
        return 0

    _all, nonempty = load_segments(args.script)
    (run_dir / "narrations.json").write_text(
        json.dumps({"segments": nonempty}, indent=2)
    )
    print(f"[bakeoff] {len(nonempty)} non-empty narration segments "
          f"from {args.script}")

    # References
    refs: dict[str, Path] = {}
    refs["synthetic"] = ensure_synthetic_ref(refs_dir)
    refs["paragraph"] = refs_dir / "reference_paragraph.txt"
    if not refs["paragraph"].exists():
        refs["paragraph"].write_text(REFERENCE_PARAGRAPH)
    user_ref_path = refs_dir / "reference_user.wav"
    if args.record:
        refs["user"] = record_user_ref(refs_dir, device=args.record_device)
    elif args.user_ref:
        refs["user"] = normalize_user_ref(args.user_ref, refs_dir)
    elif user_ref_path.exists():
        refs["user"] = user_ref_path
    have_user_ref = "user" in refs
    if not have_user_ref:
        print("[bakeoff] no user reference — skipping clone-user variants "
              "(provide --user-ref or --record)")

    # Variant matrix, sequential
    results = []
    for provider in args.providers:
        _w, _deps, supports_clone = PROVIDERS[provider]
        variants = ["stock"]
        if supports_clone:
            variants.append("clone-synth")
            if have_user_ref:
                variants.append("clone-user")
        for variant in variants:
            results.append(
                run_variant(provider, variant, run_dir, refs,
                            args.timeout, args.skip_existing)
            )

    (run_dir / "run.json").write_text(json.dumps(
        {
            "script": str(args.script),
            "providers": args.providers,
            "user_ref": have_user_ref,
            "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "results": results,
        },
        indent=2,
    ))

    out = build_html(run_dir, args.script, have_user_ref)
    ok = sum(1 for r in results if r["status"] == "ok")
    print(f"\n[bakeoff] {ok}/{len(results)} variants ok")
    for r in results:
        if r["status"] != "ok":
            print(f"  FAILED: {r['provider']}/{r['variant']} "
                  f"(see {r['provider']}-{r['variant']}/worker.log)")
    print(f"\n[bakeoff] open {out}")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
