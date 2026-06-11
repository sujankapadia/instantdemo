# M3: Voice & Brand — pocket-tts voice picker + universal pronunciations (pocket-tts-only GUI)

## Context

Fourth PRODUCT_PLAN.md milestone (#59 + #54 rescoped). Voice becomes
durable project state instead of CLI flags: `<project>/tts.json`
(voice / cloned reference / pronunciations) drives the renderer, the
segment re-render path (today HARDCODED to kokoro af_heart in TWO
places — re-render AND delete-segment), and a new GUI Voice &
Pronunciation dialog. Branch: `feature/voice-and-brand`.

Settled (user-confirmed):
1. **Pocket-tts is the provider, full stop (GUI).** Default + only
   GUI-surfaced provider. Kokoro/google/elevenlabs/piper remain
   usable via CLI flags (developer persona) but get NO GUI surface,
   NO config-schema special-casing, NO new code paths. No silent
   fallback: pocket-tts unimportable → explicit friendly error
   (#58 style) suggesting pip install.
2. **Settings dialog** (header gear, currently unwired) hosts
   Voice / My Voice / Pronunciation tabs; New Project form shows a
   one-line voice summary + "Change…".
3. **Pronunciations: respelling only — persona-simple.** Pocket-tts
   (text → tokenizer → audio LM) has NO G2P/phoneme layer: the
   entire #54 phoneme machinery (IPA lexicon, inline markup, static
   miss detection) is inapplicable. And it's the wrong abstraction
   for the PM persona anyway. M3 ships `{match, say}` entries —
   "type it like it sounds" — applied as a speech-text transform
   before synthesis, verified by a LISTEN-CHECK preview button (the
   only verification possible without a phoneme layer). NO ipa
   field, NO detection, NO auto-resolver, NO tier files. Display
   text (storyboard/demo-script/captions) NEVER mutated — the
   speech/display split is computed at synthesis.
4. Bake-off findings 7–8 = cloning UX law: file upload (not
   capture), duration+silence validation, instant preview/A-B,
   consent affirmation, iteration-friendly.

Verified facts: renderer runs IN-PROCESS via phases/render.py
(`render_main(argv)` in executor) — plumbing is argv; three
conflicting defaults today (render.py --tts default "google",
cli/RunRequest "kokoro") — unified by the config module; pocket_tts
importable in dev python; 26 stock voices enumerable at
`pocket_tts.utils.utils._ORIGINS_OF_PREDEFINED_VOICES` (private API —
vendor a snapshot, try live import first); Header.tsx:135 gear has
no onClick; Layout hardcodes tts:'kokoro' at 3 startRun sites;
provider fns call sys.exit(1) on import failure (in-process callers
must catch SystemExit).

## tts.json schema (project root, sibling of intent.json — #59)

```json
{
  "provider": "pocket-tts",
  "voice": "alba",
  "ref_wav": ".instantdemo/voice-reference.wav",
  "pronunciations": [
    {"match": "Evernote", "say": "Ever note"},
    {"match": "ENEX", "say": "ee-nex"}
  ],
  "consent": {"given": true, "at": "<iso>"}
}
```

`provider` kept in the schema (forward compat + CLI override
visibility) but the GUI never asks. `ref_wav` overrides `voice` when
set; project-relative so fixtures travel with their voice.

## Key decisions

- Module `src/instantdemo/tts_config.py` (intent.py pattern):
  dataclasses TTSConfig + PronunciationEntry {match, say};
  load/load_or_default/save; resolve_ref_wav;
  `apply_pronunciations(text, entries)` (case-sensitive literal
  `\b`-bounded re.sub, list order); `speech_segments(segments,
  entries)` (copies; originals untouched); POCKET_STOCK_VOICES
  snapshot + live-import helper. (No KOKORO_VOICES, no
  kokoro_lexicon.)
- Legacy projects (no tts.json): uniform default pocket-tts/alba
  everywhere incl. re-render; no provenance sniffing.
- Precedence: explicit CLI flag > tts.json > built-in defaults. TTS
  argparse flags get default=None sentinels; resolution extracted
  into pure `_resolve_tts(args, config)` for unit tests.
- `Context.tts: str | None = None` (None = use project config);
  RunRequest.tts → `str | None = None`; GUI stops sending tts.
- render.py: new `--tts-config <path>` flag (fallback: tts.json next
  to the script); new single dispatcher `generate_audio(segments,
  tmp_dir, config, project_dir, env_path)` — applies
  speech_segments, resolves ref, dispatches to the existing 5
  provider fns UNCHANGED (speech transform benefits all of them for
  free; no kokoro-specific additions); main() Phase A uses it;
  Phases B/C/D keep ORIGINAL segments. Print resolved provider/voice
  at start.
- phases/render.py: argv = [script, -o, out, --tts-config,
  <project>/tts.json] + [--tts, context.tts] only when not None.
- segments.py: `_generate_project_audio(project, segments, tmp_dir)`
  helper (load_or_default → render.generate_audio); replaces BOTH
  hardcoded kokoro calls (_do_re_render_audio:414,
  _do_delete_segment:310); catch SystemExit → 503 w/ guidance.
- New `server/routes/voice.py`:
  - GET /api/project/voice → config + persisted/ref_exists +
    pocket_installed (find_spec — no torch import) + stock voices
  - PUT /api/project/voice (partial: voice/pronunciations; 409
    during runs)
  - POST /api/project/voice/reference (multipart + consent form
    field REQUIRED → 422): ffprobe duration (reject <4s/>120s),
    ffmpeg decode + peak/RMS silence check (reject < −50 dBFS),
    convert to mono WAV at .instantdemo/voice-reference.wav, update
    config + consent timestamp. Humanized 422 details.
  - DELETE reference (clears ref_wav + consent)
  - POST /api/project/voice/preview {text?, voice?, use_reference?,
    pronunciations?} → wav bytes (stock previews, clone A/B,
    per-entry listen-check). Module-level model cache +
    threading.Lock (executor threads); voice-states cached per
    prompt. Gated-weights ValueError → 403 w/ HF unlock
    instructions; ImportError/SystemExit → 503.
- pyproject.toml: `pocket-tts` extra; add to all-tts.
- Frontend: api/voice.ts + useVoice + VoiceDialog (tabs: Voice =
  stock-voice list w/ per-voice ▶ preview (Blob → Audio); My Voice =
  upload + consent checkbox + 422 surfacing + A/B preview (clone vs
  current stock) + remove, "a voice like yours" copy + quiet 10-30s
  phone-recording guidance; Pronunciation = match→say rows ("type it
  like it sounds") + add/remove + per-row ▶ listen-check). NO
  provider dropdown, NO speed slider, NO IPA field. "pocket-tts not
  installed" renders an inline install hint. Header gains
  onOpenSettings (wire gear). Layout: voiceOpen state, drop tts from
  3 startRun sites. NewProjectForm: TTS block → voice summary +
  "Change…" (threaded via NewProjectModal).
- #54: comment rescope (universal respelling shipped pocket-tts-
  first; ALL phoneme machinery — lexicon, inline markup, detection,
  auto-resolve — deferred indefinitely as Kokoro-only; heteronym fix
  under pocket-tts = respell/reword). KOKORO_PRONUNCIATIONS.md gets
  an M3 status note. #59 closed by PR.

## Tests (spec-first hook: specs BEFORE test files)

- test_tts_config: load/save/malformed/defaults; apply_pronunciations
  (boundary hit, NO partial-word "Evernotes", case-sensitive,
  multi-entry order, multi-word match, empty); **speech_segments
  leaves originals unmutated — the display-text guarantee, most
  important assertion in M3**; ref_wav resolution.
- test_voice_routes (TestClient + tmp project): GET shapes; PUT
  partial/invalid/409; upload consent-missing→422, 1s-clip→422,
  anullsrc-silent→422 (ffmpeg-generated fixtures), valid→stored;
  DELETE; preview (monkeypatched synth) returns audio/wav; 503 path.
- Re-render dispatch tests: monkeypatch provider fns; tts.json →
  assert generate_audio_pocket_tts called w/ config voice/ref (both
  re-render AND delete paths); a kokoro tts.json (hand-written, CLI
  persona) still dispatches correctly.
- _resolve_tts precedence unit tests (flag > config > default).
- Smoke: smoke_segment_edit + tts.json + Evernote→Ever note entry
  (manual listen; kokoro config for CI cheapness is fine — the
  dispatcher is provider-agnostic). L5: user picks a pocket stock
  voice → uploads their bake-off sample w/ consent → A/B → adds
  pronunciation + listen check → renders the Evernote demo in their
  cloned voice → confirms storyboard/segments still display
  "Evernote".

## Sequencing (gate after each)

| # | Step | Gate |
|---|------|------|
| 1 | tts_config.py + transform + tests | pytest green |
| 2 | render.py dispatcher + --tts-config + sentinels + speech split | resolution tests; manual render w/ respelling audible |
| 3 | Plumbing: Context.tts None, cli/runs/phases | full suite green (Context default = regression risk) |
| 4 | segments.py config dispatch (both paths) | dispatch tests; smoke_segment_edit w/ tts.json |
| 5 | voice.py routes + app wiring + pyproject extra | voice route tests green |
| 6 | GUI: VoiceDialog + header/Layout/form wiring | npm build + tsc; manual dialog walkthrough |
| 7 | Docs + #54/#59 comments + L5 sign-off (cloned-voice render) + PR | smokes green; user sign-off |

## Risks

- pocket-tts/torch in server process → lazy imports in workers only;
  find_spec for availability; memory acceptable (local single-user).
- sys.exit(1) provider fns → catch SystemExit at in-process call
  sites (cleanup to exceptions = out of scope).
- Default flip (google/kokoro → pocket-tts) → friendly error path +
  resolved-provider print + dialog warns via installed flag.
- Upload false-rejects → lenient thresholds (−50 dBFS, 4s floor),
  named failure messages, one-click retry.
- Preview latency → first-call model load 3-5s w/ spinner; cached
  after.
