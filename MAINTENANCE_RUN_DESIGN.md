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

## Detection: mechanical first, agent only on failure

The expensive way to find drift is to re-run the rehearsal agent
over everything. The CI-shaped way is a two-tier check:

1. **Mechanical replay (no LLM, ~$0).** Replay the demo script with
   plain Playwright. Selectors that miss and waits that time out
   flag their scenes.
2. **Grounding assertions.** The selector can survive while the
   words go stale (the label case). Phase 4 already verifies
   narration claims against the live app during rehearsal — it just
   throws that knowledge away. Persist it: each verified scene
   records the visible-text facts its narration depends on
   (`assert_text: [{selector, text}]` on the scene). The mechanical
   replay checks them as cheap text assertions.
3. **Scoped repair.** Only flagged scenes go to an agent, chapter by
   chapter (M7's unit of work), with Level 1/2 authority and BLOCKED
   as the stop. Untouched chapters never enter a prompt.

Cost shape: a green build is **zero agent calls** — Playwright +
TTS cache + ffmpeg. A one-label release costs one bounded repair
call and one segment re-voice. The full creative pipeline runs only
when a human decides the demo should *say something new*.

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
