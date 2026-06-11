# Product Plan: The Polished End-to-End Flow

**Status:** Draft for discussion (2026-06-10). The implementation plan
for the product flow synthesized in `PRODUCT_DIRECTION.md` — the
journey a polished standalone product (pointable at a live app today)
owes its user at each step, the build plan that gets there from the
current codebase, and the decisions to settle before cutting code.

**Related:** `PRODUCT_DIRECTION.md` (§3 persona, §3.6 feedback as the
interface, §5 source-free experiments), issues #7, #14, #16, #18,
#38, #50, #51, #54, #59, #60, `docs/local-tts-models.md` (bake-off).

---

## The product, end to end

**"Point it at your running app. Approve a storyboard. Get a narrated
video in your voice. Give notes to revise."**

### Step 1 — New Project (the first 60 seconds decide everything)

Inputs on one screen: **app URL** (required), **brief** in plain
words, optional **product one-pager** (paste/upload), optional
**login**, optional **source dir** (developer enrichment, per the
graded evidence model). On URL entry: instant pre-flight —
reachability probe and a **screenshot within seconds** ("this is the
app I found — right?"). The polish bar: zero pipeline vocabulary, and
the user sees something *visual* before they've finished typing the
brief.

### Step 2 — Understand (source-free exploration, watched live)

The productionized version of what was proven in
`PRODUCT_DIRECTION.md` §5: browser-driven exploration with the jail
on, read-only guardrails, brief+docs as evidence. The user watches a
**filmstrip populate live** (the screenshots-during-run idea earning
its keep). It ends not with an artifact but with an **intent
confirmation card**: "Here's what your app does and what I think the
demo should show — audience, tone, scenes. Edit anything." The blank
form becomes a yes/and.

### Step 3 — The storyboard gate (the product's center of gravity)

Plan + selectors + dress rehearsal compose into one screen:
**numbered scenes, each with its rehearsal screenshot, narration,
estimated duration**, and any flagged uncertainty in human language
("I found 5 active sessions — is this the data you want filmed?").
Inline edits, scene vetoes, then **Approve → render**. Phase rail and
markdown artifacts demote to a "details" drawer for the developer
persona.

### Step 4 — Voice & brand (once per project)

Voice picker: stock voices with instant audio previews, or **"use my
voice"** — upload a 10s recording (the bake-off's finding 8 written
into UX law: file upload over in-app capture, silence/level
validation on upload, instant preview synthesis, consent checkbox).
Plus pronunciations — "how do you say your product's name?" with a
listen-check.

### Step 5 — Render & deliver

Sectioned recording for resilience, and the output package v1: MP4
**plus captions** — which are nearly free, since
`segment-timing.json` + narration text *is* an SRT file. Logo bug
and outro card next.

### Step 6 — Review & notes (the loop that makes it sticky)

Video and storyboard side by side. Notes on segments/sections/the
whole demo → tier classification → **consequence preview before
spend** → one regeneration per tier → **v2 with a what-changed
diff**. Global constraints graduate into `intent.json`. The project
accumulates a house style; demo #3 comes out right the first time.

---

## The build plan

Six milestones, each independently shippable, ordered so each
de-risks the next:

| # | Milestone | What's new | What's already proven | Size |
|---|---|---|---|---|
| **M0** ✅ 2026-06-10 | **`storyboard.json` — the data contract** | One canonical structured artifact (scenes: narration, action, selector, screenshot ref, status, flags) that phases 2–5 write/read, replacing markdown-parsing between phases | The action-contract bug taught us exactly why: implicit contracts break when input distributions shift. Close them *before* building UI on top | M |
| **M1** ✅ 2026-06-10 | Source-free Phase 1 + pre-flight + intent proposal | New phase1 prompt w/ browser tooling, jail default-on for it, screenshot streaming (new SSE event), intent-confirmation endpoint | The entire §5 experiment series; the harness is the prototype | M |
| **M2** ✅ 2026-06-10 | Storyboard UI | React storyboard view over `storyboard.json`; rehearsal screenshots; triage→scene notices; phase rail demoted | GUI scaffolding, SSE, triage panel all exist — this is a re-skin plus screenshots | L |
| **M3** ✅ 2026-06-10 | Voice & brand (#59 + #54 generalized) | Per-project TTS config, voice picker w/ upload validation + consent, pronunciation respelling layer with the **speech-text/display-text split** | pocket-tts provider shipped; bake-off findings 7–8 are the UX spec | M |
| **M4** (rescoped 2026-06-10) | Revision essentials | **Versioned takes** (snapshot per render/revision, A/B previous-version toggle, restore) + a whole-demo "adjust style/pacing" pass (one text box → one rewrite/pace change → one audio re-render; no classifier) | Takes design + SDK-no-tools pattern from the M4 design review; segment edit/delete/re-voice already cover per-segment revision directly | M |
| **M5** | Sections (#50) → **the feedback milestone** | Section schema in storyboard/script, per-section re-plan + re-record, chapter UX; structural notes ("redo the middle", "also show X") become affordable scoped operations | The §2.1 analysis (PRODUCT_DIRECTION.md); render concat is straightforward ffmpeg; the M4 design review's answers-card voice + regenerate-with-brief door carry over | L |
| **M6** | Output package v1 | SRT captions (must use *display* text — depends on M3's split), logo overlay, outro card | All ffmpeg-layer, no agent work | S |

**Why this order:** M0 first because everything downstream
(storyboard UI, notes, sections) reads or writes that schema, and
retrofitting a data contract under a shipped UI is the expensive
version. M1 before M2 because the storyboard UI should be built
against what source-free exploration actually produces. M3 before M4
because tier-2 notes ("different voice," "slower") need voice config
to exist.

**The M4 rescope (2026-06-10 design review):** the original
notes-with-classifier design was demoted after working it end to
end. Two findings: (1) for per-segment wording the user knows, the
existing direct edit beats a note — describing a sentence to an LLM
is slower than typing it; pronunciation/voice/cut likewise already
have more direct affordances. (2) The revisions with real value —
show something else, fix what's on screen — all require re-exercising
the app and re-recording, which notes structurally can't do; and
re-recording is cheap ($0.09/~2min) — what's expensive is
RE-PLANNING, and the fix for that is sections. So M4 keeps only the
genuinely-new pieces (takes; the one note kind that beats direct
manipulation — whole-demo style/pace) and M5 becomes the feedback
milestone proper. Everything before it was designed sections-aware
so it slots in rather than rewrites.

**Cross-cutting polish bar** (applies to every milestone, as
acceptance criteria): no pipeline vocabulary user-facing; every wait
shows progress *and* something visual; every failure states its next
action in plain language; every spend is previewed; everything is
versioned and revertible.

**Testing per milestone:** extend the smoke-script pattern —
`smoke_storyboard.py` (M0/M2 contract), the bake-off stays as the
voice harness (M3), a notes-classification eval set (M4, ~20 labeled
example notes), one new fixture per milestone as the regression
baseline, in the spirit of the source-free fixtures.

---

## Pre-M0 decisions — SETTLED 2026-06-10

1. **storyboard.json cutover: big-bang on a branch.** Phases 2–5 all
   switch in one branch; markdown artifacts become rendered views of
   the structured artifact. No dual-write transition period — that's
   where contract bugs breed.
2. **GUI-first; CLI frozen.** The new flow (intent proposal,
   storyboard gate, notes) ships in the GUI only. The CLI stays the
   developer/debug surface at today's capability — the persona
   doesn't use a CLI. (Revisit only if a CI/headless use case for the
   new flow materializes, e.g. the #51 refresh loop.)
3. **Phase 3 stays intact through M1.** Merging it into Phase 4 is a
   cleanup for after M0 lands, when storyboard.json makes phase
   boundaries cheap to move. Limits M1's blast radius.
4. **Versioned takes: plain directories, keep last N.**
   `.instantdemo/takes/v1/…`; retention policy keeps the most recent
   N takes (N configurable, default ~3) with videos pruned oldest-
   first; storyboard/script JSON is small enough to keep for all
   takes (full text history survives even when video is pruned).
