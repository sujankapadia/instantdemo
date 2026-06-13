# The Maintenance Run

**Status: designed, not built.** Issues are labeled
[`maintenance-run`](https://github.com/sujankapadia/instantdemo/labels/maintenance-run).
This doc is the contract they share.

## The problem

Today the pipeline is **generate-first**: every run re-explores the
app, re-plans the narrative, and re-writes the narration. That is
correct for the first film and wrong for every film after it. Run
the same pipeline twice against the same app and you get two
different demos — different chapter names, different sentences,
different pacing — because phases 1–2 are creative and
non-deterministic by design.

A demo that lives in a build pipeline has the opposite need. The app
changes a little on every release — a button label, a layout shift, a
color, occasionally a real feature — and the demo should change
**exactly as much as the app forces it to and no more**. If the
"Save" button becomes "Save changes", the one sentence that says
"click Save" should now say "click Save changes", spoken in the same
voice, in the same place, in an otherwise identical film.

## The core inversion

On a cold start, the storyboard is the *output* and the app is the
input. In a maintenance run, that flips:

> **The existing storyboard is the contract. The app is what
> changed.**

A maintenance run never executes phases 1–2. Narration and flow
cannot drift run-to-run because they are never regenerated — they
are only ever **repaired**, and repair is bounded by the authority
ladder Phase 4 already has:

| Level | Drift | Repair | Narration |
|---|---|---|---|
| 1 | Selector misses (DOM moved/renamed) | Swap selector (+fallbacks) | Untouched |
| 2 | App's visible words no longer match the narration | Reground the affected sentence to what the app shows | One sentence changes |
| BLOCKED | The flow itself no longer exists | None — surface it | Untouched; build fails with a humanized report |

The button-label case is precisely Level 2, which exists today
(`smoke_phase4_rehearsal.py --scenario 5c` provokes it
deliberately). What's missing is a run mode that applies the ladder
to an **existing** board instead of a freshly planned one.

## What we're actually checking (and what we're not)

A maintenance run is **not** diffing the app against itself — a
thousand things change between builds (CSS, a feature three screens
away, a backend refactor) and none of them matter. It checks one
narrow thing: **does this demo still faithfully represent the app?**
A demo is a bet — *do these actions, see these states, here's what
they mean* — and the run re-settles that bet against a new build.
The demo declares a small set of dependencies; the check verifies
ONLY those; everything outside the set is free to change. The
assertion set IS the demo's contract with the app surface, and
nothing more — which is what keeps the check cheap and tractable.

## The assertion taxonomy (three layers)

A scene stacks an **action** (anchored by a selector), the **state**
it produces, and **narration** that makes **claims** about that
state. Faithfulness decomposes into three checkable layers, and the
layer that fails determines the repair authority:

| Layer | Question | Failure → repair |
|---|---|---|
| 1 **Reachability** | Can the action still be performed? (selector resolves, interactable) | selector drift → **Level 1** (swap selector; narration untouched) |
| 2 **Consequence** | Does the action still produce the expected state? (pill changes, list re-renders, N rows) | behavior drift → **BLOCKED** (a feature changed; human regenerates) |
| 3 **Truthfulness** | Do the narration's claims still match the screen? | label/wording drift → **Level 2** (reground that one sentence) |

Layer 3 is a spectrum by checkability: **structural** claims ("click
**Save**" → a button labeled Save exists) and **relational** claims
("the list **narrows**" → row count dropped) are mechanically
checkable and gate the build; **quantitative** claims ("**fifty**
notes") are the volatile-data trap; **subjective** claims ("looks
just like Evernote") aren't checkable at all. Only the stable end
gates; volatile values are advisory; subjective claims aren't
asserted.

Layers 1 and 2 are the spine — almost entirely mechanical, and
where most real breakage lives. The whole volatile problem lives in
exactly one cell (Layer-3 quantitative), handled by a mechanical
threshold (100→102 is data; 100→0 is drift) and engineered out at
generate time (don't pin volatile specifics in narration).

## Detection: strictly mechanical; LLM is repair-only

**Decision (design discussion):** the drift check is one mode —
**mechanical, no LLM escalation inside detection.** This beats
letting the check escalate "ambiguous" cases to a cheap model on
all three axes: simplicity (no confidence-scoring/escalation policy;
detection never costs money), cost (CI spend is flat and
predictable, not variable with build noise), and correctness (the
*damaging* drift — a broken path — is caught mechanically 100%; the
rare residue is covered by the backstop below, not per-run spend).

1. **Mechanical replay (no LLM, ~$0).** A deterministic harness —
   a stripped renderer that drives but doesn't record — replays each
   scene's action via the renderer's existing `_dispatch_action` +
   `_wait_first_match` (try candidates, first that resolves). The
   script IS the existing demo-script; nothing is composed.
2. **Assertion evaluation (no LLM).** After each action, evaluate
   that scene's captured predicates against the live DOM with plain
   queries (`query_selector`, `inner_text`, `count()`). This works
   because the prior verified state is written down (the
   assertions), so "is it still correct?" collapses from a
   *judgment* (what Phase 4 needs an LLM for) into a *comparison*.
   The expensive part moved from runtime-LLM to generate-time
   capture. Per-scene verdict: ok / selector-drift / behavior-drift
   / text-drift / volatile-advisory.
3. **Scoped repair (LLM, summoned per failure).** Only a *failed*
   scene at a *repairable* layer spends a token — try captured
   fallbacks mechanically first; only then an LLM probe (L1) or a
   one-sentence reground (L2); behavior drift is BLOCKED with no
   repair call. Chapter-scoped (M7's unit); untouched chapters never
   enter a prompt.

**The blind spot, named honestly:** a green mechanical check means
"no declared dependency broke," NOT "provably still perfect" — a
button whose selector and label are unchanged but that now *does*
something different can pass. The backstop is a **full re-rehearsal
(the real Phase 4) the operator triggers** (`--full`, or a cadence
they set), where the false negatives get caught at a predictable,
bounded cost — never per-run escalation. Certainty is something you
*buy when you want it*, not a tax on every run.

**Where the correctness actually comes from** — input quality, not
runtime cleverness: (a) the #88 schema must force **evaluable
predicates, not prose** (`{selector, check, expected, layer,
volatile}`) so the mechanical check is *sufficient*; (b) a Phase-2
narration discipline — don't pin volatile specifics unless they're
a stable archive (the 500-note case) — which kills the #1
false-positive source before it exists.

Cost shape: a green build is **zero agent calls** — Playwright +
TTS cache + ffmpeg. A one-label release costs one bounded repair
call and one segment re-voice. The full creative pipeline (or the
`--full` re-rehearsal) runs only when a human asks for the thorough
answer.

## What re-records vs. what's reused

- **Video: always re-recorded, full pass.** Layout and color changes
  are invisible to selectors but visible to viewers; the film must
  show the current app. Recording is the deterministic, LLM-free
  part — this is cheap. (Splice-by-chapter only applies when visuals
  are guaranteed unchanged, which a code change can't guarantee.)
- **Narration text: byte-identical** unless a grounding assertion
  failed and Level 2 repaired that sentence.
- **Audio: cached per segment**, keyed by hash of
  (narration text, provider, voice, cloned-ref, pronunciations).
  Unchanged narration is bit-identical across runs as a hard
  property, not a hope. (Today a full render re-synthesizes
  everything; local TTS is *mostly* reproducible but not
  guaranteed.)
- **The build artifact:** the film, the SRT, and a **drift report**
  in the register `phase4-diff.md` already speaks: "scene 9:
  narration updated to match the renamed button; 24 scenes
  unchanged." The storyboard.json and .srt diffs are PR-reviewable
  text — that's what makes the demo auditable in a pipeline at all.

## CI surface

`instantdemo maintain --url <preview-url> --project <dir>` (the
project directory — storyboard, tts.json, takes — is the durable
state; in CI it lives in the repo or restored cache):

- Exit 0: no drift, or all drift auto-repaired at Level 1/2. Film +
  SRT + drift report written.
- Exit nonzero: BLOCKED scene(s). Drift report names the broken
  flow and carries the humanized suggestion; nothing is improvised.
  A human reviews and either fixes the app or runs a scoped chapter
  re-plan (the M5b Revise machinery) to accept the new reality.
- Policy is explicit, not inferred: auto-repair Level 1/2 by
  default, `--report-only` to repair nothing, never auto-replan
  without opt-in.

Takes (M4) remain the audit trail: every maintenance run that
changed anything snapshots the prior film first.

## How we test it

Determinism claims need determinism tests. Three tiers:

1. **Unit (spec-first, as always):** assertion persistence
   round-trips through storyboard.json; the replay checker flags
   exactly the mutated scene; the audio cache hits on identical
   inputs and misses when any key component changes; the repair
   merge touches only flagged scenes.
2. **Drift fixture harness:** the smoke fixture app
   (`scripts/smoke_phase1_explore.py` style) gains env-controlled
   drift switches — `DRIFT_LABEL=1` renames a button,
   `DRIFT_LAYOUT=1` reorders a panel and changes colors (no text
   change), `DRIFT_REMOVE=1` deletes a flow. A
   `smoke_maintain.py` runs the matrix:
   - **No drift** → exit 0, zero agent cost, narration and audio
     hashes identical to the prior run, video re-recorded.
   - **Label drift** → exactly one scene's narration changes (the
     SRT diff is one line), exactly one segment re-voiced (every
     other audio hash identical), one Level 2 entry in the drift
     report.
   - **Layout drift** → exit 0, zero narration changes, fresh video
     showing the new layout.
   - **Removed flow** → exit nonzero, BLOCKED report naming the
     flow, film untouched.
3. **L5 (user-driven):** run `maintain` twice against an unchanged
   app and confirm the two films are indistinguishable (narration,
   voice, timing); then rename one visible label in the fixture and
   confirm the rebuilt film differs in exactly one spoken sentence.
   This is the milestone's definition of done — "only what
   absolutely needs to change, changes" is the thing the user
   watches for.

## Why this is the SaaS story

"Re-run on every release" is where recurring pricing earns itself
(see PRODUCT_DIRECTION.md). The maintenance run is also the cheapest
compute the product has: its steady state is deterministic replay +
render, with agent spend proportional to actual drift. The M7
chapter machinery (bounded prompts, scoped re-plan, fail-fast) was
built for exactly this consumer.

## Build order

The issues sequence roughly as: grounding assertions (the data),
mechanical replay (the detector), the maintain entry point (the
repairer), audio cache (the determinism hardener), CI surface +
drift report (the product). The drift fixture harness lands with the
detector so every later piece is born tested.
