# TTS docs update + voice-cloning bake-off harness

## Context

The "voice per project" feature for the PM persona hit Kokoro's ceiling
(~3 usable English voices, no cloning). Research this session verified a
new generation of local, permissively-licensed cloning models — notably
**Pocket TTS** (MIT, 100M, CPU-only, 5s cloning), which breaks the old
"CPU-fast XOR cloning" trade. Before designing a brand-voice tier, we
need ears-on evidence: render the same demo narration through the
candidates, including cloned voices, and listen side by side.

Two deliverables:
**A.** Update `docs/local-tts-models.md` with the verified June 2026
landscape (license column — the decisive dimension).
**B.** Build a bake-off harness under `scripts/explore/` producing a
static HTML listening page.

User decisions (locked): models = Pocket TTS + Chatterbox + OmniVoice
vs Kokoro af_heart baseline; clone refs = both synthetic (af_heart) and
user-recorded; deliverable = HTML listening page. No engine changes.

---

## Part A: docs/local-tts-models.md update

Rewrite the comparison table with verified data + license column:

| Model | License | Cloning | Hardware | Verdict for InstantDemo |
|---|---|---|---|---|
| Pocket TTS (Kyutai) | MIT (code) / CC-BY-4.0 (weights), HF repo click-through gated | 5s sample | 2 CPU cores, 6x realtime | Top candidate: Kokoro-class footprint + cloning |
| Chatterbox (Resemble) | MIT | 5s | GPU; Mac = CPU fallback (slow) | Quality benchmark; watermarked output |
| OmniVoice (k2-fsa) | Apache 2.0 | zero-shot + voice design (ref transcript required) | MPS supported, Qwen3-0.6B base | Broadest capability |
| MOSS-TTS family | Apache 2.0 | zero-shot; Nano 0.1B is CPU-first | 8B needs GPU/MLX-8bit | Nano = round-2 candidate |
| Qwen3-TTS | Apache 2.0 | ~3s + NL voice design | consumer NVIDIA | GPU-bound; watch |
| VoxCPM2 (OpenBMB) | claimed free commercial — **verify license text** | yes + design | unverified | Watch |
| F5-TTS | weights CC-BY-NC ✗ | — | — | Ruled out (non-commercial) |
| IndexTTS-2 | custom Bilibili, commercial needs written auth ✗ | — | — | Ruled out |
| XTTS-v2 | CPML non-commercial ✗, Coqui defunct | — | — | Ruled out |
| Fish Speech | old: Apache 2.0 / new S2 Pro: research-only | yes | GPU | Pinned to old weights |

Keep the existing "Current providers" section; add note that the
bake-off harness (Part B) is the evaluation path. Update the title date.

## Part B: bake-off harness

### Architecture

```
scripts/explore/tts_bakeoff.py                  (orchestrator — repo env)
   │  subprocess per provider: uv run --no-project --with <pins> worker_X.py
   ▼
scripts/explore/tts_workers/
   ├── bakeoff_common.py        (stdlib-only: protocol args, timing, stats writer)
   ├── worker_kokoro.py         (repo env; baseline + --make-reference mode)
   ├── worker_pocket_tts.py
   ├── worker_chatterbox.py
   └── worker_omnivoice.py
   ▼
scripts/explore/out/tts-bakeoff/<run>/index.html  (self-contained, relative links)
```

Isolation is mandatory: Chatterbox pins `torch==2.6.0`/`transformers==5.2.0`,
OmniVoice wants `torch==2.8.0` — they can never share an env. `uv run
--no-project --python 3.11 --with …` gives cached ephemeral envs; the
instantdemo dev env is untouched (only Kokoro runs in it, via
`sys.executable`).

### Verified per-provider APIs (from READMEs/model cards)

- **Pocket TTS** (`pip install pocket-tts`): `TTSModel.load_model()`;
  `get_state_for_audio_prompt("alba" | "ref.wav")` — stock and clone are
  the same call; `generate_audio(state, text)` → torch tensor; rate via
  `tts_model.sample_rate` (read at runtime, don't hardcode). Preflight:
  HF repo is gated — catch 401/403 → "accept conditions at
  huggingface.co/kyutai/pocket-tts, set HF_TOKEN".
- **Chatterbox** (`pip install chatterbox-tts`):
  `ChatterboxTTS.from_pretrained(device)`; `model.generate(text)` =
  stock, `model.generate(text, audio_prompt_path="ref.wav")` = clone;
  `model.sr` (24k). Mac: monkey-patch `torch.load` to force
  `map_location` (issue #85); try MPS → fall back to CPU on placeholder
  errors; record actual device in stats. Slowest model; ~2.5–3 GB.
- **OmniVoice** (`pip install torch==2.8.0 torchaudio==2.8.0 omnivoice`):
  `OmniVoice.from_pretrained("k2-fsa/OmniVoice", device_map="mps")`;
  `generate(text=…)` stock, `generate(text=…, ref_audio=…, ref_text=…)`
  clone — **ref transcript required**; returns np arrays @ 24 kHz.
- **Kokoro** (repo env): mirror `render.py:289` but **concatenate all
  pipeline chunks** instead of `break` after the first. Side-note to
  surface during implementation: render.py's `break` may truncate
  multi-chunk narrations — check whether KPipeline ever yields >1 chunk
  for our narration lengths; if yes, that's a latent engine bug to file.

### Worker protocol

```
worker_X.py --narrations narrations.json --out-dir <dir> \
            --variant stock|clone [--ref-wav P --ref-text-file P] [--device auto|cpu|mps]
```
- `narrations.json`: `{"segments":[{"index":0,"text":"…"},…]}` — only
  non-empty narrations, fixture indices preserved.
- Worker: load model once (timed) → synthesize each segment (timed) →
  `segment_NN.wav` (native rate, mono, 16-bit) + `stats.json`; non-zero
  exit + stderr on failure. Orchestrator tees output to `worker.log`.
- `stats.json`: provider, variant, device, sample_rate, model_load_s,
  per-segment {chars, synth_s, audio_s, rtf, bytes}, totals, package
  versions, notes (e.g. "mps failed → cpu").

### Variant matrix (8 columns)

kokoro/stock · pocket/stock(alba) · pocket/clone-synth · pocket/clone-user
· chatterbox/stock · chatterbox/clone-synth · chatterbox/clone-user
· omnivoice/stock · omnivoice/clone-synth · omnivoice/clone-user

### Reference samples

- `REFERENCE_PARAGRAPH` constant (~30–35 words ≈ 10–12s spoken) in the
  orchestrator — one paragraph serves as both clone source and
  OmniVoice's required `ref_text`.
- Synthetic: `worker_kokoro.py --make-reference` renders it with
  af_heart → `refs/reference_synthetic.wav` (objective fidelity test:
  clones try to mimic the baseline column).
- User: reads the same paragraph. Primary path `--user-ref <any format>`
  (QuickTime/Voice Memos OK; normalize via
  `ffmpeg -ac 1 -ar 24000 -sample_fmt s16`). Optional `--record` helper
  via ffmpeg avfoundation (countdown + paragraph printed); document
  QuickTime as the reliable path (TCC mic permissions). If no user ref:
  skip clone-user variants with a notice.

### Orchestrator flow & flags

`--script` (default: `fixtures/source-free-evernote-jailed-2026-06-09/demo-script.json`,
8 segments, 1 empty → 7 synthesized) · `--providers` subset (incremental
first runs; downloads are GB-scale) · `--skip-existing` (resume) ·
`--timeout` (default 30 min/worker) · `--rebuild-html`.
Run variants **sequentially** (fair timing, memory). Tolerate per-variant
failure: record in `run.json`, render a red error cell.

### HTML page

Single static file, vanilla HTML/CSS + tiny JS, relative `src` only:
- Header: fixture, date, hardware, both reference players + the
  reference paragraph text (judges read it while listening to clones).
- Table: row per fixture segment (empty ones grayed), col per variant,
  `<audio controls preload="none">` (~70 players — preload off is
  required). "Play column" button per variant (sequential via `ended`).
- Stats block: load time, total synth, overall RTF, rate, bytes, device,
  versions per variant; failures link to worker.log.
- Keep native sample rates — no resampling (don't adulterate what we're
  judging); browsers handle it. Optional `--loudnorm` post-pass later if
  loudness differences distract (default off, not in v1).

### Edge cases

- Disk budget ~8–10 GB (weights: pocket ~0.5 GB, chatterbox ~3 GB,
  omnivoice ~2 GB + up to 3 torch builds in uv cache). HF cache shared.
- First-run stats are download-dominated: report timing from a
  `--skip-existing` second pass, or note it in the HTML footer.
- Chatterbox output is Perth-watermarked (fine; note in footer).
- Sampling nondeterminism: set seeds where exposed; else note reruns vary.
- Add `scripts/explore/out/tts-bakeoff/` to `.gitignore` (audio output).

### Implementation sequence

1. `bakeoff_common.py` + `worker_kokoro.py` (both modes) — end-to-end
   testable with zero new installs.
2. Orchestrator skeleton + HTML from kokoro-only matrix; verify in browser.
3. `worker_pocket_tts.py` (smallest download; proves uv isolation +
   cloning protocol against the synthetic ref).
4. `worker_omnivoice.py`, then `worker_chatterbox.py` (most fragile) last.
5. User records ref → full run → review page.

## Verification

- `uv run --no-project … worker_pocket_tts.py` works from a clean shell.
- Synthetic ref ≈10s, 24 kHz mono, sounds like af_heart.
- Each variant dir: 7 WAVs + valid stats.json; ffprobe durations sane.
- index.html opens via `file://`, players lazy-load, directory survives
  being moved (relative links).
- Stats show the device actually used (catches silent CPU fallbacks).
- `--skip-existing` rerun touches no WAVs; `--providers X` runs only X.
- Killed worker → failure recorded in run.json, HTML still renders.
- Part A: docs table renders, claims match the cited sources.

## Files

- `docs/local-tts-models.md` (rewrite table — Part A)
- `scripts/explore/tts_bakeoff.py` (new)
- `scripts/explore/tts_workers/{bakeoff_common,worker_kokoro,worker_pocket_tts,worker_chatterbox,worker_omnivoice}.py` (new)
- `.gitignore` (one line)
- Reference (read-only): `src/instantdemo/render.py:289-320`,
  `fixtures/source-free-evernote-jailed-2026-06-09/demo-script.json`
