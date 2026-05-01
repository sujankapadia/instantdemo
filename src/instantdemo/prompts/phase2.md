Design the demo's story arc.

You will write a narrative plan as markdown — not JSON. (The JSON
script is produced in a later phase using the technical details
gathered after this one.)

Use these defaults unless the user has specified otherwise:
- **Tone**: casual (developer advocate)
- **Audience**: technical (developers)
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
