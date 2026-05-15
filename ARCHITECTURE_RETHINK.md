# Architecture rethink: is there a simpler, more reliable approach?

Authored 2026-05-13 after the M3 shakedown, the #5 / #49 prompt
work, and the #50 / #51 enhancement-issue filings. Open question:
given what we've built and what we've learned, is the current
6-phase pipeline the right architecture, or is there a fundamentally
better way to solve the same problem?

## TL;DR

The current architecture isn't *wrong*, but it's a sophisticated
plan-then-reconcile dance designed to compensate for the LLM not
being able to trust its own browser-driving. That assumption is
becoming dated. A single-loop **explore-first, narrate-second**
agent — Playwright as a tool, model drives and observes in the
same loop — would likely be simpler, more reliable, and would
collapse most of the brittle reconciliation layer.

Recommendation: prototype the explore-first version on a small
scope before investing further in the current pipeline. Most of
the codebase (GUI, data model, edit-and-re-render, TTS, ffmpeg)
transfers either way.

---

## The inversion: explore-first, narrate-second

The current pipeline is **top-down**:

> plan a narrative → infer selectors → hope they match → probe
> the live app to catch mismatches → render

Phase 4 (Explore) exists because Phase 2's narrative and Phase 3's
selectors can independently be wrong, and reconciliation happens
after the fact. Each LLM stage compounds risk. The whole
multi-phase verification dance is built to compensate.

A **bottom-up** flow inverts this:

1. **Explore** — agent drives the live app (autonomously, or with
   a user-specified goal), finds flows, records a selector +
   screenshot trace as it goes
2. **Choose** — pick the trace to turn into the demo
3. **Narrate** — write narration paired to the actual recorded
   trace
4. **Render** — TTS + ffmpeg (unchanged)

### Why this is more reliable

- **Selectors come from things actually clicked**, not inferred
  from source. No "plan vs. reality" mismatch — the
  reconciliation problem disappears at the source.
- **Narration grounds in observed UI state**, not predicted state.
  The whole class of bugs #5 and #49 were filed for (AI-tells,
  overclaim) largely evaporates — the model can't overclaim about
  something it watched happen.
- **The trace is verified-executable before any narration exists.**
  Phase 4's job collapses to "did this run cleanly: yes/no."
- **Drift detection (#51) becomes "re-run the trace"** — purely
  mechanical, no LLM judgment required.
- **The 6 phases collapse to roughly 3.**

### What survives unchanged

- `intent.json` (now informs exploration goals instead of narrative
  planning)
- Segment data model
- Inline edit + audio-only re-render loop
- TTS pipeline (Kokoro, ElevenLabs adapters)
- ffmpeg orchestration / `_remux_with_per_segment_extension` /
  cut-segment
- GUI shell (project state, run controls, segments list, video
  player)
- SSE event stream, run dispatcher, state.json

Probably 60% of the existing codebase transfers cleanly.

### What gets harder

**Autonomous exploration is a hard agent capability.** The model
has to be a good user — knowing when to click vs. read, when a
flow is interesting vs. boring, when to stop. The frontier moved
a lot in 2025-2026 with Stagehand, browser-use, and Computer Use,
but it's not solved. Adopting the explore-first architecture means
betting that this capability is reliable enough — or accepting that
the user has to steer more (which may not be a bad thing; see
section on autonomy below).

---

## Two questions upstream of architecture

### 1. Is video the right output format?

Market signals (from the #50 research pass) say **interactive HTML
demos beat video on both onboarding *and* maintenance**. HTML is
easier to patch than re-recording. If the wedge is "regenerable
demos for DevRel and docs-as-code" (the #51 target), interactive
HTML might be the more defensible output than MP4.

The same trace-based pipeline can produce both — a recorded trace
of `(action, selector, screenshot, narration)` tuples can render to
either an MP4 (TTS + ffmpeg) or an interactive HTML walkthrough
(screenshots with overlays, optional audio per step, click-through
navigation).

But you have to pick one to optimize. Video is the more "magical"
demo (and what users imagined when they first heard the pitch);
interactive HTML is more defensible and more aligned with where the
market is actually paying.

### 2. How autonomous should the agent be?

"From a URL, auto-generate a demo" is the most magical pitch but
also the most failure-prone. "User describes a flow in natural
language, agent executes it" is way more reliable today.

The most successful adjacent tools all bias toward **user-directed
execution**, not autonomous discovery:

- Playwright codegen — user clicks, tool records
- Stagehand — user describes an action ("click the login button"),
  tool figures out the selector
- browser-use — agent executes user instructions, doesn't pick what
  to do
- Claude Computer Use — agent does what the user asks, doesn't
  decide what to demo

Fully-autonomous "pick a flow and demo it" might be a 2027 product.
User-directed "demo this specific flow, here's a one-paragraph
description" is shippable today and probably has better failure
modes (failures are interpretable as "the user's description was
ambiguous" rather than "the agent misjudged what was interesting").

InstantDemo currently sits awkwardly between the two poles. It
accepts a goal (`intent.goal`) but then does heavy autonomous
codebase analysis + narrative invention. The user has limited
steering after submission, and the failure modes are precisely
where the agent over-extrapolated from limited signal.

A user-directed explore-first design would be:

> User: "Show the active sessions page, hover one card to explain
> what it shows, then click into the conversation."
> Agent: \[drives the browser, records, narrates\]

That's much more reliable than what the current architecture
attempts.

---

## What's good about the current architecture

Worth saying explicitly so this isn't just a critique:

- **The phase decomposition is a defensible design** for the
  problem as originally framed (LLM can't drive a browser
  reliably; have it write a plan, then mechanically verify and
  render). Most pre-2026 "AI demo" architectures look like this.
- **Phase 4 (Explore) was the right addition.** It's exactly
  the right move within the current paradigm — adding a
  reconciliation step between plan and render.
- **The structured findings + GUI triage pattern is good
  product design** regardless of the underlying architecture.
  It would survive an architectural inversion (the explore-first
  version still has trace-execution failures that benefit from
  the same triage UX).
- **The intent.json + segment data model is portable.**
- **The inline narration edit + audio-only re-render loop is
  the genuinely novel iteration mechanic** and would be the
  star feature of any architecture.

---

## Honest assessment

The current architecture is a sophisticated way to compensate for
the LLM not being able to trust its own browser-driving. Phase 4
exists because Phase 3's source-based selector reasoning can be
wrong. The plan-then-reconcile dance is the reasonable thing to
build when you assume the model can't directly observe what it's
doing.

**But that assumption is becoming dated.** The frontier model +
tool-use combo can now drive a browser and observe results in the
same loop. If the model can drive and observe in one loop, the
whole "plan ahead, verify after" multi-phase structure is solving
a problem that no longer exists.

What I'd actually build if starting fresh today:

- A single Claude Agent SDK loop with Playwright as a tool
- System prompt: "explore this app toward this goal, record what
  you do, narrate as you go"
- Output: a JSON trace of `(action, selector, screenshot,
  narration)` tuples per segment
- Deterministic render layer at the end (TTS + ffmpeg, unchanged
  from today)

That's maybe 30% of the current codebase, with the brittle parts
(Phase 3 selector inference, Phase 4 reconciliation, the entire
phase-dispatch machinery, the cost-delta tracking, the
session-id-per-phase juggling) gone.

---

## Recommendation

**Not "throw out the current work."** Most of it transfers, and
you've learned a ton building it. The data model, GUI, edit loop,
render layer, and intent.json all stay. The agent SDK plumbing
and Playwright integration stay. What changes is the *structure
of the agent's job*: from "director who plans then executes
through three intermediate documents" to "user who explores then
describes."

**Concrete next step: prototype the explore-first version against
the same shakedown scenario** (active-sessions page, exclude
recently-ended sessions). Maybe a weekend of work:

1. Single-script prototype: Claude Agent SDK + Playwright tool +
   the same `intent.json` as input
2. Output: a JSON trace in the same segment format you already
   use, so the existing render layer can consume it unchanged
3. Compare the result to the saved fixture from this week
4. Decide based on the comparison

**The risk of *not* prototyping** is continuing to refine a
6-phase pipeline when the next year of model capability gains
makes a 1-loop pipeline strictly better. Better to find that out
cheaply now, before investing in #50 (sections), more agent
prompts, or further phase-pipeline polish.

If the prototype is worse, you'll know precisely why the
multi-phase approach is necessary and can keep building with
conviction. If it's comparable or better, you've found a much
simpler architecture and you can plan a migration over the next
few weeks with most of the GUI/render/data-model intact.

---

## Open questions to revisit after the prototype

- Does the trace-based agent reliably produce a coherent flow
  without explicit narrative planning, or does it wander?
- How does cost compare? (Naïve guess: lower, because no
  separate codebase-read phase, but the exploration loop
  could be longer.)
- Does the trace format need additional structure (timing
  hints, scroll points, hover-vs-click distinctions) that
  exploration doesn't naturally produce?
- For the interactive-HTML output question: is the trace
  expressive enough to drive both MP4 and interactive output
  from the same data, or do they diverge?
- Where does `intent.excludes` live in the new design — as
  a system prompt constraint, as a post-trace filter, or
  built into the exploration loop?
