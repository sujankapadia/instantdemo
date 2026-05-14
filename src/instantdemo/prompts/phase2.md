Design the demo's story arc.

You will write a narrative plan as markdown — not JSON. (The JSON
script is produced in a later phase using the technical details
gathered after this one.)

Use these defaults unless the user has specified otherwise:
- **Tone**: casual (developer advocate)
- **Audience**: non-technical (general user, not a developer)
- **Terminology**: use product/feature names from the codebase analysis

Plan the narrative:
- **Pick one compelling flow** that shows the core value proposition.
- **Use as many segments as the flow naturally needs.** A flow with many
  distinct beats deserves more, smaller segments; a flow with a few
  atomic actions can be tight. Don't pad and don't compress.
- **Aim for visual dynamism.** The viewer should see the camera move,
  not just stare at one static page while narration plays. Include
  scrolls, hovers, or wait-on-detail segments where they help the
  story breathe.
- **Lead with the payoff** — show the impressive result early, then
  explain how you got there.
- **Narration defaults**: short sentences, present tense, spoken-word
  style, no jargon, contractions OK.
- Some segments may have no narration (e.g. login, scrolling to
  position) — flag those.

For each segment, write:
1. A short title
2. The proposed action (navigate, click, scroll, wait, fill, hover, evaluate, etc.)
3. Draft narration text (or note "(silent)" if appropriate)
4. The target at a high level (page name or URL, descriptive locator) — exact CSS selectors and timing land in the next phase

Number the segments. Keep each segment compact — three to five lines is plenty.

## Narration style — anti-patterns to avoid

These are tells that make narration sound AI-generated. They apply
unconditionally; `intent.addenda` can override a specific one if the
user asks.

1. **Em-dash dependency.** In spoken English, em-dashes force an
   "and-then-this" cadence that doesn't read naturally when narrated.
   Use periods. Em-dashes are fine occasionally for emphasis; heavy
   use is a tell.

2. **AI vocabulary.** Words like "delve", "remarkable", "leverage",
   "robust", "seamless" rarely show up in natural speech. If you'd
   be embarrassed to say it out loud to a colleague, don't write it.

3. **Marketing reframes.** If the product calls it a "Bookmarks
   page," call it a bookmarks page. Don't reach for synonyms
   ("shelf", "moments", "your library") to sound more polished. Use
   the product's own terms.

4. **Pushy benefit claims.** "Perfect for your workflow," "exactly
   what you need," "saves hours." The viewer decides if it's useful;
   your job is to show it, not assert it.

5. **Adjective stacking.** "Powerful, intuitive dashboard." One
   descriptor at most; usually none.

6. **Rhetorical question openers.** "Ever wonder how X?" "What if
   you could Y?" Reads as old-infomercial.

7. **Hype intros.** Don't dress up what's about to be shown as
   exciting or magical — the content speaks for itself. *Patterns
   to avoid (illustrative, not exhaustive): "the magic part",
   "here's the kicker", "where it gets cool", "the cool thing is".*

8. **Repeated transition openers.** Conversational lead-ins ("let's
   X", "now we Y") sound like verbal tics when used across many
   segments. Vary them, or drop the preamble — most segments don't
   need one. *Patterns to limit (illustrative): "let's jump",
   "let's pop", "and now", "okay so".*

## Ground every factual claim

Anchor each factual claim to something concrete: a route in source,
an element on the page, a value observed in Phase 1 or Phase 3. If
you can't point to where the claim is grounded, rephrase it as
observation rather than assertion.

**Source code is evidence.** A value, interval, default, route, or
config observed in source counts as grounded even when not visible
in the rendered demo. The principle is "have evidence", not "be
visually evident". If a fact is in source and adds context the
viewer would care about, narrate it.

- Grounded shapes (have evidence somewhere):
  - Descriptions of visible structure: "this section lists X",
    "each row shows Y"
  - Observed behavior: "clicking opens Z"
  - Values or intervals read from source — narrate them with the
    actual value, not as a generic claim
- Ungrounded shapes (no evidence anywhere):
  - "automatically X" with no auto behavior in source or runtime
  - Overgeneralizing from one example: "every Y", "all your Z"
  - Unverifiable benefit claims: "perfect for X", "saves you hours"
  - Invented intervals, frequencies, or time windows

Don't add capabilities the user didn't ask for and you didn't see.
Don't invent frequencies, time windows, or benefit statements
without evidence in source or the live app. **When in doubt, drop
the claim** — a shorter accurate narration beats a longer
embellished one.
