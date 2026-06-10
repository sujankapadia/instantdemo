# Product Direction: From Developer Tool to Living Demo Studio

**Status:** Draft for discussion (2026-06-09). Synthesizes a codebase
analysis (renderer, pipeline, GUI) and a product-persona exercise into
a candidate future direction. Nothing here is committed; this is the
document to argue with.

**Related docs:** `ARCHITECTURE.md` (current state),
`ARCHITECTURE_RETHINK.md` (explore-first inversion question),
`DRESS_REHEARSAL_DESIGN.md` (Phase 4 design),
`GUI-DECISIONS.md` (v1 GUI scope).

---

## 1. Where the product is today

InstantDemo generates narrated demo videos from a URL + source code
via a 6-phase agent pipeline, with a CLI and a local GUI. It works
well for 2–5 minute demos (8–30 segments) produced by a developer who
has the repo checked out, the app running locally, and a Python
toolchain installed.

Three structural facts shape everything below:

1. **Recording is monolithic.** Phase 6 records the entire demo in
   one continuous Playwright session (`render.py:865-927`). One
   failed selector at segment 40 of 50 loses the whole take.
   `DRESS_REHEARSAL_DESIGN.md` already names ~20–30 segments as the
   fragility breakpoint.
2. **The pipeline has restart cliffs.** Bad inputs (unreachable URL,
   missing seed data) are discovered 10+ minutes and ~$0.50 in, at
   Phase 4. A Phase 4 findings-JSON parse failure or a Phase 5
   wrong-path write halts the pipeline with no retry turn.
3. **The product assumes a developer.** Source code is required
   (Phases 1 and 3 read it), installation requires pip + brew + npm,
   and the UI speaks in phases, artifacts, and selectors.

---

## 2. Technical findings (the "make it better" analysis)

### 2.1 Longer videos: the monolithic recording is the wall

For 5–15 minute demos (20–50 segments):

- **Single-take fragility.** No checkpoints; a mid-walk selector
  timeout, unexpected redirect, or unclosed modal kills the entire
  recording. Recovery is a full re-record.
- **Resource accumulation.** Chromium runs for the full demo length;
  DOM/heap/connection state accumulates across the session.
- **O(N) re-render cost.** Audio-only re-render regenerates TTS for
  *all* segments every time (`segments.py:392-398` — no cache). A
  one-word edit on a 50-segment demo costs minutes of Kokoro time.
- **No per-segment visual re-render.** The video is atomic; the only
  visual operations are full re-record and frame-accurate delete.

**Direction: sections (issue #50) as the spine**, in this order:

1. **Per-segment audio cache** — hash narration + voice + speed →
   cached WAV in `.instantdemo/audio-cache/`. Turns a one-segment
   edit from O(N) into O(1). Smallest change, biggest immediate win.
2. **Sectioned recording** — make sections explicit in the script
   schema (each section starts from a known URL/state). One
   Playwright context + WebM per section, concat at the end. A
   failure in section 3 keeps sections 1–2; "regenerate section"
   becomes a button; browser session length is capped.
3. **Per-section dress rehearsal** — the same sectioning makes Phase
   4 naturally checkpointed; long demos converge section-by-section
   instead of in one giant 3-iteration loop.

Sections also yield user-facing structure for free: chapter markers,
a chapter list in the GUI, and per-section regeneration when the app
changes (pairs with stale-detection, issue #51).

### 2.2 Seamlessness: kill the three restart cliffs

- **Pre-flight validation** (trivial, do first): before Phase 1, probe
  the URL, check the source dir exists, check ffmpeg/Playwright are
  present. Removes the worst first-run experience.
- **One-turn format-retry loops:** if Phase 4's findings JSON doesn't
  parse (`explore.py:356-361`) or Phase 5 writes to the wrong path
  (`script.py:72-76`), send a single corrective follow-up turn before
  giving up. Converts pipeline-halting errors into hiccups.
- **Self-healing retries (issue #10):** Phase 4 BLOCKED findings
  already contain a diagnosis. When the failure is clearly upstream
  (selector wrong → re-run Phase 3 with failure context injected),
  do that retry automatically once before surfacing the triage panel.
- Smaller seams: "re-run from Phase N onward" (issue #38); roll back
  `state.json` status when a phase crashes mid-flight (currently
  stuck at `in_progress` forever).

### 2.3 Magic: close the loop between seeing and doing

- **Screenshots during the run.** Phase 4 already drives a browser;
  have the rehearsal script save a frame per segment at the settle
  point (after the action completes and the selector check passes),
  and stream them into the GUI via SSE as they land. The user watches
  the demo assemble itself instead of reading tool-call logs.
  - **Value, honestly stated:** (a) a human catches doomed runs —
    wrong account, stale seed data, cookie banner — at minute 1
    instead of after a ~$1, ~7-minute run; selector checks pass on
    all of those, only a human frame-glance catches them. (b) Failure
    screenshots are the best diagnostic evidence the triage panel can
    show. (c) Frames make a long opaque wait legible to non-technical
    users — the only feedback channel they can interpret.
  - **Phase 6: extract, don't capture.** Don't screenshot during the
    recording loop (it would perturb recorded timing); extract
    per-segment keyframes from the finished video with ffmpeg +
    `segment-timing.json`. These persist as segment thumbnails and
    feed the vision QA pass (issue #8).
  - Minimal scope if the filmstrip feels like too much: failure-only
    screenshots + post-render thumbnails.
- **Audio overflow is silently destructive.** When edited narration
  outruns the recorded clip, the API reports `overflow=true` but the
  UI does nothing and narration gets cut. Offer a one-click choice
  before re-render: freeze last frame to fit (the `tpad` mechanism
  from issue #37 already exists) or shorten the text.
- **Triage panel should resolve, not report.** "I found a working
  alternative selector — apply and re-render this section?" Phase 4
  already has selector-swap authority; extend it to post-hoc triage.
- **Pace + voice controls:** per-segment pace nudge or global
  slower/faster slider (`pause_after_ms` is the documented fix but
  isn't editable in the GUI — issue #18); implement Kokoro
  pronunciation overrides (issue #54 — a demo that mangles the
  product's own name breaks the spell).
- **Smart defaults at cold start:** pre-fill source path from
  cwd/git; have Phase 1 *propose* the intent (goal/audience/focus
  inferred from README + routes) so the blank form becomes a
  confirmation step.
- **Post-recording vision check (issue #8), elevated:** for long
  videos the probability that some segment shows the wrong thing
  approaches 1. A cheap vision pass over per-segment keyframes turns
  "watch the whole video to QA it" into "review 2 flagged segments."
  Reuses the screenshot/keyframe work above.

---

## 3. The persona exercise: product owner / marketer

### 3.1 Who they are

A PM at a 50-person SaaS company, or a product marketer who owns
launch content. Their recurring jobs: "Feature X ships Tuesday — I
need a 90-second video for the launch email, a 30-second cut for
LinkedIn, and the onboarding video needs updating because the nav
changed." They produce demo content on a **release cadence**, not as
a one-off.

Their deepest, chronic pain is not making videos — it's that **every
video starts rotting the day the product changes**. They quietly stop
linking to their own demos out of embarrassment.

### 3.2 Hard facts that invert current assumptions

- **They don't have the repo.** No `--source`; they have a staging
  URL with demo data. Selectors must come from observing the live
  app — which makes the explore-first inversion in
  `ARCHITECTURE_RETHINK.md` a *persona requirement*, not just an
  architectural preference.
- **They can't pip install anything.** The current on-ramp
  (pip + brew + playwright + npm) filters them out entirely. They
  need a hosted web app, or at worst a signed desktop app.
- **Their staging app is behind a login.** Saved-session auth
  (issue #7) is table stakes, not an edge case.
- **They review scripts, not selectors.** "FAIL_SELECTOR on segment
  7" is noise. But they already have a review ritual: script /
  storyboard approval before production. **Phase 2's narrative plan
  is a storyboard** — currently presented as a developer artifact;
  for this persona it is the single most important screen in the
  product.

### 3.3 The app they'd want

One line: **"Describe the demo in plain English, point at your
staging URL, approve the storyboard, get the video — and the video
stays current as your product changes."**

Positioning: between Loom (manual recording — instantly stale,
requires a human performance) and the interactive-demo platforms
(Arcade / Storylane / Navattic / Guidde — capture-based, but the
capture is manual and goes stale the same way). The differentiated
promise: *the agent drives the real app*, so regeneration is a
button, not a re-shoot. (Competitive landscape from general
knowledge; worth a proper teardown before betting on the wedge.)

### 3.4 What "seamless" means to them

**Creation.** Paste a URL, log in once (session saved), type a brief
in their own words: "show how a team lead sets up the new approval
workflow; upbeat; under 2 minutes; don't show admin settings." No
seven-field intent form — the agent explores the app, drafts the
storyboard, and proposes the intent back for confirmation.

**The storyboard gate.** Before any rendering: numbered scenes, each
with a screenshot of the actual screen (Phase 4 rehearsal shots),
the narration line, and an estimated duration. Edit narration in
place, cross out a scene, "add a beat about pricing here." Approve →
render. This one screen replaces the phase rail, artifacts, and
triage panel — everything translated into storyboard vocabulary
(issue #14, end-user mode, taken to its conclusion).

**Output.** Not "an MP4" — a package: 16:9 *and* vertical cuts,
captions by default (most social/email video plays muted), correct
pronunciation of the product name (#54 is brand-critical here),
brand kit applied (logo bug, intro/outro card, brand colors on the
cursor highlight, approved voice). A share link, not a file download.

**Iteration in their language.** "Make the middle section snappier"
(pace → `pause_after_ms`), "the voice sounds salesy" (tone → scoped
Phase 2 re-run), "re-do just the dashboard part — we shipped the
redesign" (re-record one section). The section abstraction (#50) is
what makes the last request sane instead of a full re-shoot.

**The moat: demos as living documents.** Connect the staging URL; on
every release (CI webhook, or a weekly probe), the agent re-walks the
approved storyboard against the live app — issue #51,
stale-detection, is exactly this. Nothing drifted → silence.
Something drifted → "Your 'Approval Workflow' demo is out of date —
the settings page moved. Here's a refreshed draft; narration
unchanged. Approve to publish." The PM's job changes from *producing*
videos to *approving refreshes*. Capture-based competitors can't
follow: their unit of regeneration is a human re-recording. This is
the feature that converts a one-shot tool into a subscription.

### 3.5 The three inversions

| # | Today | For this persona |
|---|-------|------------------|
| 1 | Source code required; Phases 1+3 read the repo | Live-app exploration as the primary path (validates prototyping the `ARCHITECTURE_RETHINK` inversion before deepening the 6-phase machinery) |
| 2 | Phases as UI (rail, artifacts, triage) | Storyboard as UI; the pipeline stays but the user never sees it. Existing machinery (triage findings, rehearsal screenshots, segment editing) re-skins onto storyboard scenes |
| 3 | One-shot generation | Subscription to freshness: #51 + #50 + saved auth (#7) compose into the recurring-revenue feature; the one-shot generator becomes its onboarding flow |

Almost nothing here is new invention — it's the existing backlog
(#7, #11, #14, #16, #50, #51, #54) re-prioritized around a buyer with
a budget and a recurring pain, instead of around the developer who
happens to be able to run the tool today.

### 3.6 Feedback as the interface: notes → tiered revision → durable intent

The persona doesn't think in "which phase do I re-run" — they think
in **notes**, the way they'd give feedback to a video agency: watch
the cut, leave comments, get v2. The polished revision UX takes that
literally.

**One feedback surface.** All feedback is a note attached to what
they're looking at — a segment ("this line overclaims"), a section
("this part drags"), or the whole demo ("too formal"; "never show
customer names"). Free text, their vocabulary. No forms, no phase
buttons, no tier selector.

**The system classifies each note into the cheapest sufficient
revision.** The tiers map onto machinery that already exists:

| Tier | Note sounds like | What regenerates | Machinery |
|---|---|---|---|
| 0: Direct edit | (types replacement text) | One segment's audio | Shipped (PATCH + audio re-render) |
| 1: Line notes | "less jargon", "shorten this" | LLM rewrites that line, structure fixed → audio | Small prompt + existing re-render |
| 2: Global style | "more playful", "slower", "different voice" | All narration rewritten within fixed structure → audio; or pure TTS config (voice/pace), no words at all | Phase-2-style pass + #59 voice config + #18 pace |
| 3: Coverage/structure | "drop the settings part", "add the export flow", "lead with X" | Re-plan from intent onward — scoped to a section once #50 lands | #38 + #50 |

Design rules that make it feel polished:

1. **Show the consequence before the spend.** "This changes what's
   covered — I'll re-plan and re-record section 2 (~3 min, ~$0.40);
   other sections won't change." Cost/time control without pipeline
   vocabulary. For ambiguous notes ("make it warmer" — the words or
   the voice?), disambiguate by *previewing both interpretations* —
   at clone RTF ~0.21, audio previews are effectively free.
2. **Notes graduate into durable intent.** "Never show customer
   names" is not a one-off fix — it's written into `intent.json`
   (excludes/addenda) so every future regeneration and every #51
   auto-refresh honors it. Feedback trains the project's brief; after
   a few demos the project has an accumulated house style and new
   demos come out right the first time. This is the compounding-value
   loop.
3. **Speak in versions, not re-runs.** v1 → notes → v2 → approve.
   Keep the prior take, show "what changed since v1" (the Phase 4
   diff machinery already produces exactly this artifact for its own
   revisions), allow revert. Batch semantics: five notes on one
   viewing → one regeneration addressing all five (group by tier,
   one pass per tier), not five sequential re-runs.

Architectural note: this tier taxonomy is the same one Phase 4
already uses internally (Level 1 selector swap / Level 2 regrounding
/ BLOCKED structural) — pointed in the other direction, with the
human as the revision source instead of the rehearsal. It's the
unifying mechanism behind #14, #16, #18, #38, #50, and the
storyboard gate (§3.4). Tracked as a vision issue.

---

## 4. Priority roadmap

Near-term items stand on their own merits regardless of the persona
bet; later items are sequenced so each one builds on the last.

### Now (engineering quality, persona-agnostic)

1. **Per-segment audio cache** — ~an afternoon; prerequisite for
   pleasant long-video editing.
2. **Pre-flight validation + one-turn format-retries (Phases 4/5)** —
   removes the worst failure cliffs for very little code.
3. **Pronunciation overrides (#54)** — design doc already written;
   protects output quality in every scenario.

### Next (the structural investment)

4. **Section abstraction (#50)** — sectioned recording + per-section
   rehearsal + per-section regenerate. Makes long videos viable and
   is load-bearing for both "re-do the dashboard part" and the
   living-demos loop. Deserves a real design pass.
5. **Rehearsal screenshots streamed to the GUI** — the highest
   perceived-magic-per-effort change; also the foundation of the
   storyboard screen.
6. **Overflow UX + per-segment pace (#18) + triage-that-resolves** —
   polish that protects output quality.

### Later (the persona bet — decide deliberately)

7. **Explore-first prototype** (`ARCHITECTURE_RETHINK.md`) with no
   `--source` — validates the no-repo path.
8. **Storyboard-first UI** (issue #14 endgame) on the existing
   FastAPI/React surfaces.
9. **Saved-session auth (#7), captions + multi-format export, brand
   kit.**
10. **Stale-detection → auto-refresh loop (#51)** — the moat;
    requires 4, 7, and 9.

### Decision points before committing to "Later"

- Prototype explore-first *before* further deepening the 6-phase
  pipeline (the rethink doc's own recommendation — the persona
  analysis strengthens it).
- Hosted vs. desktop distribution for non-developers (hosted implies
  multi-tenancy, browser isolation, and a billing story).
- A real competitive teardown of Arcade / Storylane / Guidde / Clueso
  to find the exact wedge ("agent drives the real app → regeneration
  is free" is the hypothesis to validate).

---

## 5. Experiment: source-free Phase 1 prototype (2026-06-09)

Tested the explore-first hypothesis with
`scripts/explore/source_free_phase1.py`: an agent with a **Bash-only
allowlist** (same PreToolUse-hook mechanism as `agent_client.py`),
an empty temp cwd, and no source access, prompted to build a
phase1.md-style model purely by driving the live app with headless
Playwright. Run against both fixture apps with the exact goals from
their `intent.json`, compared to the source-based `phase1.md`
baselines in the fixtures.

| App | Baseline (source) | Source-free (live app) |
|---|---|---|
| Evernote viewer | $0.29 · 35s · 16 turns | $0.19 · 109s · 7 turns |
| claude-code-analytics | $0.18 · 25s · 7 turns | $0.21 · 111s · 8 turns |

Outputs: `scripts/explore/out/source-free-phase1-{evernote,cca}.md`.

**Result: the hypothesis holds.** Comparable cost, ~4x wall time
(Playwright round-trips), and route coverage essentially complete
(8/9 routes on cca by navigation alone, plus the 9th —
`/sessions/:id` — reached via click-through). Where it differs, the
source-free output is *more* demo-useful:

- **Confirms reality instead of predicting it.** Baseline: "a note
  titled 'Marketing' would need to already be present." Source-free:
  it's the 6th item, here are its dates and opening body text, and
  there are two duplicate-titled entries to avoid matching.
- **Content-aware editorial judgment source can't make.** On cca it
  recommended *which* session card to click ("jellico-reports — short,
  readable narrative; the instantdemo card's preview is raw
  task-notification markup — less photogenic").
- **Pre-does part of Phase 3/4's work.** Working selector hints
  (`.note-item`, `active` class), automation gotchas (session detail
  has no `<h1>` — wait on the breadcrumb), SSE/networkidle warnings.
- **No implementation-detail over-grounding** (issue #52) — it can't
  mention FTS5 or API internals because it never saw them.

**Honest misses, both the same class:** observation only sees the
*current* branch of conditional UI. The cca run never mentioned the
"Recently ended" section (no recently-ended sessions existed at
exploration time), and it can't see the empty-state. Source sees all
branches; the live app shows one. Mitigations: the user's brief
(intent) names what matters, and the dress-rehearsal re-observes at
demo time anyway. Also note the prototype's safety guardrail is
prompt-level only ("read-only exploration, don't click destructive
controls") — it complied (flagged the Import button as a hazard
unprompted), but a production version needs enforcement, not
politeness.

**Verdict: viable as the primary path, pending two confirmations** —
an end-to-end run (source-free phase1 → Phases 2–6 unchanged →
compare the final MP4 against fixture quality) and a run against an
auth-walled, more conditional app. Both test apps were small, local,
auth-free, and data-rich at exploration time; n=2.

### What source-free doesn't learn (and what to pair with it)

Categories observation can't reach, split by what they affect:

*Demo quality:*
1. **Maker's framing and vocabulary** — README pitch, what features
   are called, why they exist. Evernote happened to have a tagline;
   many internal tools have zero explanatory copy.
2. **Unreachable and conditional surfaces** — unlinked routes,
   flag-gated features, branches not rendered at exploration time
   (the "Recently ended" miss), empty-states.

*Whether the run can proceed at all:*
3. **Auth credentials** — README dev logins / bypass notes. A login
   wall stops source-free cold. Biggest untested gap.
4. **Seed-data mechanics** — observation sees data that exists, not
   how to create it (import commands, fixture scripts).
5. **Operational facts** — how to start the app, ports, dev vs prod.
   Irrelevant when the app is already running (PM persona).

The fix is not reverting to repo-reading — it's a **graded evidence
model** where the live app is the one mandatory input and everything
else is additive: `brief + live app [+ docs URL] [+ auth session]
[+ source]`.

- **Richer brief (extend intent.json):** a paragraph of product
  context — what it is, who it's for, what features are called
  (plugs 1) — plus "the flow lives under Settings → Workflows"
  (plugs 2; the rethink doc's user-directed execution).
- **Docs/marketing URL as a second exploration target:** the
  README's framing job is done better by the public marketing site
  or help docs — which are *also just URLs*. Explore the app for
  structure, the docs site for vocabulary. Same mechanism, no repo.
- **Saved auth session (issue #7):** the non-negotiable companion
  (plugs 3) — without it source-free fails on most real apps.
- **Pre-flight data check at the storyboard gate:** since
  source-free can't say how to seed data, surface readiness instead:
  "I found 5 active sessions / no note titled X — is the app in the
  state you want filmed?" (plugs 4).
- **Source as optional enricher:** when a repo is available
  (developer persona), feed it in as additional evidence — hidden
  routes, all-branches visibility, terminology.

This input set — URL, login, brief, marketing page — is exactly what
the PM persona can always provide, and never includes the one thing
they can't (the repo).

### Round 2: source-free + docs (same day)

Re-ran both apps with `--docs` injecting each app's README into the
prompt as user-provided product documentation (simulating the PM
pasting a one-pager; apps weren't hosted so no docs URL). Trust rule
in the prompt: use docs for framing/vocabulary; where docs conflict
with the live app, trust the live app and note the discrepancy.

| App | Baseline (source) | Source-free | Source-free + docs |
|---|---|---|---|
| Evernote | $0.29 · 35s · 16t | $0.19 · 109s · 7t | **$0.17 · 75s · 6t** |
| cca | $0.18 · 25s · 7t | $0.21 · 111s · 8t | **$0.18 · 70s · 5t** |

Outputs: `scripts/explore/out/source-free-phase1-{evernote,cca}-docs.md`.

**Docs made it cheaper AND faster** — the README replaced the early
recon turns, so exploration went straight to the demo-relevant
screens. And the trust rule worked as designed:

- **Caught real discrepancies instead of parroting docs.** Evernote:
  flagged the port mismatch (docs say 8000, live app on 8001) and a
  stale feature claim (docs: "UI uses metadata and filters today";
  live: search verifiably hits note body text — it typed a query to
  check). cca: noted the nav label is "Active" while the H1 is
  "Active Sessions" (vocabulary precision narration needs), and an
  Import page the README doesn't list.
- **New finding class neither prior run produced:** a privacy review
  warning — the Active cards show real user prompts verbatim
  (client/colleague names); it recommended which cards were safe to
  film. That's demo-production judgment, not app analysis.
- **One watch-item: trust transfer.** The cca+docs run went narrower
  — it marked screens it didn't visit "as documented" rather than
  verifying them. Honest attribution, but docs-sourced claims that
  reach narration unverified would recreate the overclaim problem
  (#49). Rule for production: docs may guide *where to look* and
  *what to call things*; any claim that reaches narration must be
  observed.

**Confound, caught in review:** these READMEs are *developer* docs
(the Evernote one has API/Quickstart/Project Layout sections), and
the agent exploited that — its second move was `curl /api/health` +
`/api/notes` (endpoints learned from the README) to confirm the
Marketing note existed before opening Playwright. So Round 2 alone
couldn't say whether the gains came from product framing (which a PM
has) or technical leakage (which a PM doesn't). Hence Round 3.

### Round 3: sanitized one-pager control (same day)

Stripped each README to a true product one-pager — what it is, who
it's for, feature names; zero Quickstart/API/stack/ports
(`scripts/explore/out/onepager-{evernote,cca}.md`). The Evernote
one-pager deliberately preserved a product-level version of the
README's stale search claim ("search currently works on note titles
and metadata") to test discrepancy detection without technical docs.

| App | No docs | Dev README | One-pager (control) |
|---|---|---|---|
| Evernote | $0.19 · 109s · 7t | $0.17 · 75s · 6t | $0.18 · 64s · 7t |
| cca | $0.21 · 111s · 8t | $0.18 · 70s · 5t | $0.17 · 74s · 5t |

**The gains survive sanitization** — product framing alone delivers
essentially the full speed/cost benefit (the Evernote control was
the fastest of all three variants; cca was a statistical tie with
the dev README). The technical README's API shortcut was marginal,
not load-bearing: the control run discovered the API surface on its
own by observing network calls. The PM-persona claim holds.

What the dev README bought that the one-pager didn't:

- **Stronger verification reflexes.** The dev-README run *typed a
  search query* to disprove the stale claim; the one-pager run
  caught the same discrepancy but only inferred it from the search
  box placeholder. Weaker evidence, same conclusion.

What Round 3 surfaced that Rounds 1–2 didn't:

- **Per-run variance is real.** The Evernote control claimed all 500
  notes come from one source file — wrong (5 sources, 100 each;
  verified via the API). It overgeneralized from the visible top of
  the list. Earlier runs got this right by reading the Sources
  dropdown. Similarly, the Round 2 privacy warning didn't recur in
  the control. Single-run observation has noise; load-bearing facts
  need the same rule as docs claims — **verified before they reach
  narration** (the dress-rehearsal already exists to do exactly
  this, and the phase1 prompt should instruct cross-checking facts
  against a second surface, e.g. a filter/count UI, before stating
  them).

**Updated read:** the docs tier is validated *for the PM persona* —
a product one-pager alone buys the speed/cost gain, vocabulary
fidelity, and discrepancy detection. Technical docs add marginal
extras and are the developer persona's enrichment, per the graded
evidence model. brief+app+one-pager is the right default input
package.

### Round 4: end-to-end — source-free phase1 → Phases 2–6 unchanged (same day)

Planted the Evernote one-pager run's output as `phase1.md` (with the
ANSWER block prepended, smoke.py-style) in a staging project dir
containing **no source code**, then ran the unmodified CLI phase by
phase with `--source` pointing at that empty dir.

| Phase | Result | Cost · time |
|---|---|---|
| 2 Plan | Clean pass; plan *more* grounded than typical (observed facts as narration anchors, grounding-check section) | $0.09 · 20s |
| 3 Inspect | Produced excellent selectors — **but escaped the sandbox** (see below) | $0.36 · 132s |
| 4 Explore | **8/8 PASS, overall OK, one iteration** | $0.21 · 102s |
| 5 Build | Valid 8-segment script, fallback selectors carried through | $0.08 · 27s |
| 6 Render | demo.mp4, 66s; key frames verified (layout+count pill, Marketing in view post-scroll, note open with green highlight) | $0.15 · 176s |

Total ≈ **$1.07** including the source-free phase1 — parity with
source-based fixture runs (~$1.13).

**Headline finding — the verification backstop works:** Round 3's
phase1 error ("this export" / single-source overclaim) leaked into
Phase 2's narration, and **Phase 4 caught and regrounded it**
(observed the Sources dropdown listing 5 files, rewrote the line,
kept the verified 500 count). Noisy source-free observation +
dress-rehearsal = self-correcting, exactly as designed.

**Second finding — Phase 3 escaped the sandbox:** given an empty
`--source`, the agent used Glob/Grep to locate the *real* repo on
disk (`evernote-importer/static/index.html`) and source-verified its
selectors. Tool allowlists restrict *which tools*, not *where they
read*. Consequences: (a) this run is NOT evidence that Phase 3 works
source-free — that remains untested; (b) the leak is an artifact of
testing on a machine where the source exists — a PM's laptop or a
hosted runner has nothing to find; (c) any multi-tenant/hosted story
needs real filesystem isolation, not allowlists. Notably the agent
*fused* evidence: source-verified IDs plus phase1's live-observed
facts (`data-id="6"` disambiguation, scroll-container gotcha).

**Verdict:** open question 2a's first confirmation is done — a
source-free phase1 carries through Phases 2–6 unchanged to a
verified MP4 at cost parity, with Phase 4 demonstrably absorbing
phase1 noise. Remaining: a clean Phase 3 isolation test (needs path
sandboxing or a source-less machine), the cca end-to-end repeat, and
the auth-walled app test.

### Round 5: true isolation — filesystem jail + sterile re-run (same day)

Built the path jail on branch `feature/fs-jail`: the existing
PreToolUse hook now also validates *where* file tools reach, not
just *which* tools run. (Researched first: the SDK has native scoped
deny rules — `Read(/path/**)` survives `bypassPermissions` — but
they're settings-file-only, not programmatic; the hook is the right
programmatic mechanism, and hooks fire before permission modes.)
`_jail_violation()` handles Read/Write/Glob/Grep, absolute Glob
patterns, `~` expansion, relative-path resolution against cwd,
symlinks. Opt-in via `INSTANTDEMO_FS_JAIL=1`, CLI-only (the GUI
server needs the project root threaded through RunManager first).
Bash is explicitly out of scope — jailing shell needs OS sandboxing.

**Test hygiene lesson (attempt 1):** the jail held, but the agent
mined a leftover `rehearse.py` + `state.json` from the contaminated
run — and said so openly in its artifact. Two rounds, two different
evidence-scavenging paths: the agent will use ANY evidence present.
Great product instinct, brutal on sloppy test setup.

**The sterile chain (attempt 2):** only phase1.md + phase2.md +
intent.json, jail on. Results:

- **Phase 3, genuinely source-free, works** — and degrades into
  exactly the role the rethink doc predicted: a hypothesis document.
  Confirmed-live anchors used with attribution; text-engine
  selectors (`:text-is`) where markup was unknown; a `scrollIntoView`
  strategy that sidestepped the unverified container selector; and
  an explicit "unverified, probe live" list ($0.21 · 62s).
- **Phase 4 resolved every flagged unknown in one pass: 8/8 PASS**
  (Import is a real button; container is `.note-list`; title is a
  leaf `<strong>`), plus a third narration regrounding ("dates" →
  "when it was last updated" — the list shows only an Updated date).
- **Phase 6 surfaced a real latent engine bug** (not jail-related):
  Phase 5 encoded Phase 3's readiness-check *advice* as a
  non-canonical action `wait_for_selector`. Phase 5's validator
  doesn't enforce an action enum, and the renderer's fallback
  dispatch (`getattr(page, action)` with `_RESERVED_FIELDS` stripped
  from kwargs) strips the very `selector` argument the method needs
  → TypeError at segment 7 of 8, killing the whole single-take
  recording. The fallback can never work for methods whose required
  arg is a schema field name. Also a live demonstration of the
  single-take fragility cost (§2.1). **Fixed on
  `fix/action-contract`:** closed action set in `actions.py`,
  enforced in the Phase 5 prompt, Phase 5 validation (with one
  corrective round-trip to the agent), and renderer pre-validation;
  fallback dispatch removed. Live-verified: the same sterile Phase 4
  input now yields a canonical script first-try. Root-cause lesson:
  the prompt itself defined `action` as "a Playwright page method
  name" — the agent was compliant, not creative. In agent pipelines,
  implicit contracts hold only as long as the input distribution
  holds; make contracts explicit at phase boundaries so novel
  upstream regimes (like source-free) fail fast instead of
  mid-recording.
- After a one-line script patch (segment 7 → canonical `wait`),
  the render completed: **68s MP4, frames verified** (Marketing
  centered in list, note open with highlight).

**Final read on 2a:** the source-free path is now demonstrated under
true isolation, end-to-end. Phase 3's selector-inference role
collapses gracefully into hypothesis-writing; the dress-rehearsal
absorbs all deferred verification. The remaining proof points are
the auth-walled app and (optionally) the cca repeat.

### Round 6: cca end-to-end — the React app, jailed (same day)

Repeated the sterile protocol against claude-code-analytics: React
SPA, ~no test IDs, volatile data (live session cards). Fixture:
`fixtures/source-free-cca-jailed-2026-06-09`. Result: **48s MP4,
frames verified**, chain cost ~$1.02 incl. external Phase 1.

- **Phase 3 jailed: zero source citations**, text/href selectors
  from Phase 1 observations, honest "probe live" flags. Notable
  economics: $0.18 · 65s · 9 turns jailed vs $0.55 · 261s · 36
  turns for an accidental unjailed control (which spent its budget
  reading the repo to gold-plate selectors Phase 4 re-verifies
  anyway). The jail isn't just isolation — it's cheaper.
- **Phase 4: 7/8 PASS + 1 WARN, one iteration.** The WARN is the
  experiment's best work: detail page doesn't window-scroll;
  mouse-wheel scrolling proved FLAKY (worked in probe runs 1 and 3,
  silently failed in 2); Phase 4 prescribed the deterministic
  container-`evaluate`, which Phase 5/6 used and the rendered frame
  confirms. It also dropped the unverifiable liveness claim ("new
  messages show up as they happen") after 6s/10s observation
  windows showed no updates.
- **Process footnote:** the first cca attempt ran unjailed because
  the working tree was on `fix/action-contract`, which doesn't
  contain the jail (editable install runs the working tree; the env
  var was silently a no-op). Third independent confirmation that an
  unjailed Phase 3 source-hunts every time — and a reminder that
  with editable installs, "flag set" ≠ "feature present"; verify
  the branch before trusting the test.

**Both fixture apps now pass end-to-end source-free.** Remaining
proof point: the auth-walled app (gated on saved sessions, #7).

## 6. Open questions for discussion

1. Is the PM/marketer persona the bet, or is the near-term wedge the
   developer who demos their own side project (current user) — and
   does the roadmap's "Now/Next" section serve both regardless?
2. How much of the 6-phase pipeline survives the explore-first
   prototype? (`ARCHITECTURE_RETHINK.md` suggests the phases may be
   compensating for an assumption that's aging out. The §5
   experiment strengthens this: source-free Phase 1 already pre-does
   part of Phase 3's selector work, verified.)
2a. The two §5 confirmations: does a source-free phase1 fed into
   Phases 2–6 unchanged produce an MP4 matching fixture quality?
   And does source-free survive an auth-walled app once saved
   sessions (#7) exist?
3. Does "living demos" require hosting, or can a CI-installed CLI
   (`instantdemo refresh` in a GitHub Action) deliver an MVP of the
   refresh loop for developer-adjacent teams first?
4. Sections: schema-level construct (script.json gains `sections[]`)
   or purely a Phase 2/4 planning concept? The former is more work
   but is what per-section regenerate and chapter UX hang off.
5. What's the minimum brand kit that matters (logo + outro + voice?)
   before this is credible for a marketer's launch email?
