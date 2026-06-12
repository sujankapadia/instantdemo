Outline the demo film's chapters.

The audience, tone, and any other constraints are stated above —
treat them as facts about this demo. You are NOT planning individual
scenes yet: you are deciding the film's arc — the named beats a
viewer would use to describe its parts.

Rules:
- **2 to 12 chapters.** A short demo wants 2–4; a comprehensive
  walkthrough wants more. Let the brief's ambition decide.
- **Film-register names** the viewer would use ("Opening", "Finding
  a note", "The privacy story") — never pipeline or engineering
  vocabulary.
- **One or two sentences of purpose per chapter**: what it shows and
  why it's in the film. Each chapter should be one coherent beat —
  if a purpose needs "and also", it's two chapters.
- **Lead with the payoff** — the impressive result early, mechanics
  after.
- **Estimate scenes honestly** (2–8 per chapter): how many distinct
  camera moments the beat needs. Don't pad and don't compress.
- Respect the brief's excludes absolutely — nothing excluded may
  appear in any chapter's purpose.

## Output

Reason in prose first if it helps, but END your response with
exactly ONE fenced ```json block:

```json
{
  "title": "Demo title",
  "summary": "One-line description of the whole film",
  "chapters": [
    {
      "name": "Chapter name",
      "purpose": "What this beat shows and why it's in the film.",
      "est_scenes": 4
    }
  ]
}
```
