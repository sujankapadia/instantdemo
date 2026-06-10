# Local TTS Models (updated June 2026)

Open-source text-to-speech models that run locally. Any of these could
be added as a `--tts` provider in render.py.

**The decisive dimension is license** — several "open" TTS models are
non-commercial and unusable in a monetized product. Verified against
each project's actual license text / repo discussions, June 2026.

## Comparison (license-first)

| Model | License | Voice Cloning | Hardware | Verdict for InstantDemo |
|---|---|---|---|---|
| **Pocket TTS** (Kyutai) | MIT (code) / CC-BY-4.0 (weights); HF repo is click-through gated — first run needs accepted terms + HF_TOKEN | Yes — 5s sample; tone, accent, emotion, room acoustics | **2 CPU cores**, 6x realtime, 100M params | **Top candidate**: Kokoro-class footprint + cloning. Breaks the old "CPU-fast XOR cloning" trade |
| **Chatterbox** (Resemble AI) | **MIT** (incl. Multilingual + Turbo variants) | Yes — 5s sample | GPU; on Mac falls back to CPU (slow; known MPS issues) | Quality benchmark ("beats ElevenLabs in blind tests"); output is Perth-watermarked (a provenance feature) |
| **OmniVoice** (k2-fsa) | **Apache 2.0** | Yes — zero-shot; **requires transcript of the reference**; also attribute-based voice design | MPS supported; Qwen3-0.6B base; RTF 0.025 claimed | Broadest capability; 600+ languages (mostly irrelevant for us) |
| **MOSS-TTS family** (OpenMOSS) | **Apache 2.0** (Local variant confirmed) | Yes — zero-shot; 8B rated best quality | 8B needs real GPU (community MLX 8-bit port for Macs); **Nano 0.1B is CPU-first** | Nano = round-2 candidate alongside Pocket TTS |
| **Qwen3-TTS** (Alibaba) | **Apache 2.0** | Yes — ~3s sample + natural-language voice design | Consumer NVIDIA GPU | GPU-bound; watch |
| **VoxCPM2** (OpenBMB) | Claimed free commercial — **verify actual license text before relying** | Yes + voice design, 48kHz | Unverified | Watch |
| **Kokoro-82M** | Apache 2.0 | No (limited voice blending via style tensors) | CPU, <0.3s | Current default. ~3 usable English voices (af_heart A, af_bella A-, af_nicole B-); best male is C+ |
| **Fish Speech** | Split: older releases Apache 2.0 ✓ / newer S2 Pro research-only ✗ (commercial via paid API) | Yes (~10s), emotion/tone tags | GPU | Usable only pinned to older weights |
| **F5-TTS** | Code MIT, **weights CC-BY-NC ✗** (non-commercial even after fine-tuning); community permissive retrain "OpenF5" immature | Yes | GPU | **Ruled out** for product use |
| **IndexTTS-2** (Bilibili) | Code Apache 2.0, **weights under custom Bilibili license ✗** — commercial use requires written authorization | Yes (quality leader on paper) | GPU | **Ruled out** for product use |
| **XTTS-v2** (Coqui) | **CPML non-commercial ✗**; Coqui defunct | Yes (3-6s) | GPU | **Ruled out** |
| **CosyVoice2** | Apache 2.0 (unverified this pass) | Yes | GPU | Streaming-focused; not a fit |

## What this means for InstantDemo

The voice story is a three-tier ladder, all within the existing `--tts`
provider architecture:

1. **Kokoro** — default: instant, CPU-only, free, small stock voice menu
2. **Local brand voice (cloning)** — "record 10 seconds, every demo
   narrates in that voice." Candidates: **Pocket TTS** (best fit on
   paper), Chatterbox (quality benchmark), OmniVoice, MOSS-Nano
3. **ElevenLabs** — premium cloud tier (existing provider)

Caveats: all quality claims above come from launch blogs — none replace
listening. A cloning UI implies a consent step (it's a voice cloner).
The pronunciation-override design (#54) is Kokoro/misaki-specific and
needs a per-provider strategy.

**Evaluation path:** `scripts/explore/tts_bakeoff.py` — renders a
fixture's narration through Kokoro + the cloning candidates (stock and
cloned variants) into a side-by-side HTML listening page.

## Bake-off findings (2026-06-10, Apple M1 Pro 32GB)

Ran the harness against the Evernote fixture's 7 narration segments
(~70s of speech). Cloning reference: a ~11s WAV of Kokoro af_heart
reading a fixed paragraph — so clone columns can be judged directly
against the baseline column they're imitating. Listening page:
`scripts/explore/out/tts-bakeoff/<run>/index.html`.

### Measured results

| Variant | Device | RTF (lower = faster) | Ear verdict |
|---|---|---|---|
| kokoro stock (af_heart) | cpu | **0.14** | baseline |
| pocket-tts stock (alba) | cpu | ~0.2 | great |
| **pocket-tts clone of af_heart** | **cpu** | **0.21** | **great** |
| omnivoice stock (auto) | mps | 0.98 | n/a — voice roulette (see below) |
| omnivoice clone of af_heart | mps | 2.01 | great |
| pocket-tts clone of user voice | cpu | 0.21 | decent — recognizably not-quite-me |
| omnivoice clone of user voice | mps | 1.99 | decent — recognizably not-quite-me |
| chatterbox stock | mps | 9.43 | (quality moot at this speed) |
| chatterbox clone of af_heart | mps | 7.14 | (quality moot at this speed) |

User-voice reference: a single ~12s iPhone Voice Memos recording of
the fixed paragraph (peak −5.9 dB). Notably, the human clone cost the
models nothing extra — identical RTF to the synthetic-reference runs.

RTF = synthesis_seconds / audio_seconds. For this demo's ~70s of
narration: ~10s Kokoro, ~15s Pocket TTS, ~2.3min OmniVoice, ~11min
Chatterbox. Model load times excluded (reported separately in each
variant's stats.json); first-run weight downloads also excluded.

### Verdict: Pocket TTS is the pick

| Dimension | Pocket TTS | Notes |
|---|---|---|
| Speed | **RTF 0.21, CPU-only** | Same hardware story as today's Kokoro default; no GPU tier needed |
| Clone quality | Great (by ear) | Pending the user-voice test (below) |
| License | MIT code / CC-BY-4.0 weights | Commercial-safe; attribution line needed for the weights |
| API fit | Best of the bunch | Voice state computed once (`get_state_for_audio_prompt`), reused per segment — matches InstantDemo's per-segment call pattern exactly |
| Voice stability | Pinned by construction | Named voice or reference → deterministic identity across calls |
| Stock voices | 26 named voices | vs Kokoro's ~3 usable — may improve the *default* tier too, not just add cloning |

**OmniVoice** is the credible second source (Apache 2.0, clone quality
also great by ear, MPS) — but 10x slower and clone-mode-only for
stability. **Chatterbox** is out as a local provider: ~8 minutes of
synthesis for 70s of speech even on MPS, i.e. 2–3x the entire current
end-to-end render time, audio alone.

### Findings beyond the scoreboard

1. **Voice stability across calls is a hard provider requirement** the
   bake-off surfaced organically: OmniVoice's auto mode *samples a new
   speaker identity per generation call* — 7 segments came out as 7
   different voices. It has no named voice catalog; a reference WAV is
   effectively its only stable voice handle. Any provider whose stock
   mode is "sample a voice" can only be used via its
   cloning/conditioning path (InstantDemo synthesizes each segment as
   an independent call, and re-renders happen in fresh processes).
2. **Zero-shot cloning is conditioning, not training.** The reference
   WAV is encoded at inference (a ~1s forward pass), no weights
   change, same reference → same voice deterministically. Product
   implication: "set up your brand voice" is a file save, not a
   training job — the per-project artifact is just a ~10s WAV.
3. **Design-then-freeze pattern:** OmniVoice's instruct/auto modes can
   generate *new* voices from a description; saving a liked output as
   a reference WAV freezes it into a permanent custom voice (usable as
   a clone reference by any model, including Pocket TTS). A no-human-
   recording path to a unique brand voice.
4. **Pocket TTS gating is product friction, not just test friction:**
   stock voices download ungated, but the cloning weights require each
   user to accept Kyutai's HF terms + authenticate (HF_TOKEN). A
   brand-voice feature needs a guided "unlock cloning" onboarding
   step; check whether Kyutai offers a redistribution path.
5. **Chatterbox runs on MPS** (with a `torch.load` map_location patch
   — issue #85); it's just slow anyway. Its output is also
   Perth-watermarked by design.
6. **Side-finding for render.py:** Kokoro's KPipeline yielded exactly
   one chunk for every demo-length narration, so render.py's
   break-after-first-chunk is safe at current narration lengths. The
   bake-off worker keeps a tripwire note if that ever changes.
7. **The familiarity gap.** Cloning the *synthetic* voice rated
   "great"; cloning the *owner's own* voice rated "decent —
   recognizably not me." Two forces compound: clean studio-like
   synthetic references are easier inputs than phone recordings, and
   the harshest possible judge of a voice clone is the person who
   owns the voice. Product implications: (a) market the brand-voice
   tier as "a voice like yours," not "indistinguishable from you";
   (b) the setup flow should support iteration — multiple takes,
   longer samples, and an instant A/B preview — since reference
   quality is the main fidelity lever the user controls. Untested
   levers: longer (~30s) references, multiple concatenated takes,
   more expressive reads, denoising before cloning.
8. **Recording UX is the hard part of the brand-voice feature, not
   the cloning.** Getting one good 12s sample took four attempts:
   avfoundation device 0 was a virtual Teams device that recorded
   silence; device indices reshuffled when the Continuity iPhone mic
   disconnected mid-capture; the MacBook mic picked up static that
   denoising couldn't fully remove without dulling levels; the clean
   take came from iPhone Voice Memos + AirDrop. A product flow should
   prefer "upload a recording from your phone" over in-app capture,
   select capture devices by NAME never index, and verify
   levels/duration before accepting a reference (silence detection
   caught the first failure instantly).

### Open items

- ~~clone-user variants~~ Done (2026-06-10): both decent from a single
  12s phone sample; see findings 7–8. Next fidelity experiments:
  longer/multiple/cleaner references.
- Chatterbox clone-user variant unrun (academic — eliminated on speed).
- Pocket TTS language coverage (Kyutai models are historically
  English/French-centric) and a pronunciation-override strategy per
  provider (#54 is Kokoro/misaki-specific).
- Implement `--tts pocket-tts` in render.py (~40 lines on the existing
  `generate_audio_*` pattern) + per-project reference-WAV config —
  quality bar met for proceeding.

## Current TTS providers in render.py

| Provider | Quality | Cost | Local? |
|---|---|---|---|
| **Kokoro** | Near-human (af_heart) | Free | Yes |
| **Piper** | Robotic | Free | Yes |
| **Google Cloud TTS** (WaveNet) | Natural | Free tier (1M chars/mo) | No |
| **ElevenLabs** | Most natural | Paid (~$5/mo starter) | No |

## Sources

- [Pocket TTS — GitHub](https://github.com/kyutai-labs/pocket-tts) · [technical report](https://kyutai.org/pocket-tts-technical-report) · [HF model card](https://huggingface.co/kyutai/pocket-tts)
- [Chatterbox — Resemble AI](https://www.resemble.ai/learn/models/chatterbox) · [Turbo](https://www.resemble.ai/chatterbox-turbo/) · [Mac torch.load issue #85](https://github.com/resemble-ai/chatterbox/issues/85)
- [OmniVoice — GitHub](https://github.com/k2-fsa/OmniVoice) · [HF](https://huggingface.co/k2-fsa/OmniVoice)
- [MOSS-TTS — GitHub](https://github.com/OpenMOSS/MOSS-TTS) · [MOSS-TTS-Nano](https://github.com/OpenMOSS/MOSS-TTS-Nano) · [MLX 8-bit port](https://huggingface.co/mlx-community/MOSS-TTS-8B-8bit)
- [Qwen3-TTS — GitHub](https://github.com/QwenLM/Qwen3-TTS) · [announcement](https://qwen.ai/blog?id=qwen3tts-0115)
- [F5-TTS licensing discussion](https://github.com/SWivid/F5-TTS/discussions/997)
- [IndexTTS license issue #228](https://github.com/index-tts/index-tts/issues/228) · [Bilibili model license](https://huggingface.co/spaces/IndexTeam/IndexTTS-2-Demo/blob/main/INDEX_MODEL_LICENSE_EN.txt)
- [VoxCPM2 coverage (Medium)](https://medium.com/@bytefer/the-free-open-source-alternative-to-elevenlabs-is-finally-here-3cbbacd9c6b9)
