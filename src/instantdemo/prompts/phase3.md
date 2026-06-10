For each scene in the storyboard above, find the implementation details
needed to render the demo against the live app. Read the frontend source
(components, routes, layouts) to identify stable selectors and the right
wait conditions.

**Selectors — find them in the source, don't infer them.**

A file or component named `conversation-viewer.tsx` does NOT mean
the rendered element has `data-testid="conversation-viewer"`.
Component names are conventions; the rendered attribute values
are the contract Playwright sees.

### Step 1: project-level convention survey (do ONCE, upfront)

Before working through individual segments, run a small set of
broad greps to learn what this project uses. You're looking for
patterns, not exhaustive lists:

- Test ID convention: `rg "data-testid=" -c` and same for
  `data-test=`, `data-cy=`, `data-qa=`. Whichever has the most
  hits is the project's convention. If all are zero, the
  project doesn't use test IDs.
- Whether ARIA labels / role attributes are widely used (one
  count grep each is enough).

Record the result as a one-line note at the top of your output,
e.g.:

> Selector conventions in this project: `data-testid` (47 hits),
> ARIA labels used sparingly, route-based href links throughout.

**Do not repeat these broad scans per segment.** Once you know
the convention, use it directly.

### Step 2: per-segment selector lookup (efficient)

For each segment, use the conventions established above.
Prefer this order, but **stop as soon as you have a stable,
grep-verified match** — don't try every strategy:

1. **The project's test-ID convention** — if it exists, grep
   for the specific attribute literal in the component file
   most likely to render this segment's target. One focused
   grep, not a project-wide scan.
2. **Hrefs / URLs / text content** — `href="/..."` literals,
   `:has-text("Active Sessions")`. Stable for nav links and
   labeled buttons.
3. **ARIA / semantic attributes** — `aria-label=`, `role=`,
   accessible names.
4. **Structural CSS** as a last resort — `main h1`,
   `nav a:first-child`. Avoid generated class names
   (`.css-1a2b3c`, `.MuiButton-root`) — they change on every
   build.

If you can't find evidence in the source for any strategy
after a focused look, say so in one line of Notes — Phase 4
will probe the live app to fill the gap.

For each segment, include **one or two fallback selectors** you
believe could work. These don't need exhaustive verification —
they're hints for Phase 4's recovery path. Single-line notes
are enough.

**Be efficient.** A useful Phase 3 produces correct selectors
in a few grep-and-read passes per segment, not a full codebase
scan each time.

**Wait conditions**:
- For `goto` / `navigate`, what indicates the page is ready? An element
  appearing? An API response rendering?
- For pages with SSE or WebSockets, use `wait_for` with a selector — never
  rely on `networkidle` (it never resolves with persistent connections).

**Actions**: The rendering pipeline uses Playwright. The action set is
CLOSED — only these values are valid (do not invent new ones):
- `goto` or `navigate` — load a URL
- `click` — click an element
- `fill` — type into an input (needs `value`)
- `hover` — hover over an element
- `scroll` — scroll the page viewport (`window.scrollBy`; optional `pixels`)
- `evaluate` — run arbitrary JavaScript (useful for in-container scrolls
  via `document.querySelector(...).scrollBy(...)`; needs `expression`)
- `wait` — no action, narration plays over a static frame
- `select_option` (needs `selector` + `value`), `press` (needs
  `selector` + `key`), `check` / `uncheck` (need `selector`)

You may CHANGE a scene's action from Phase 2's proposal when the
source reveals a better mechanism (e.g. `scroll` → `evaluate` for an
in-container scroll) — that is part of your job.

**SPA navigation**: For single-page applications (React, Vue, etc.),
use `goto` only for the first navigation. For subsequent pages, click
a nav link to use the client-side router — full reloads make loading
skeletons appear in the recorded video.

**Pacing** (`pause_after_ms` values):
- After navigation: 1000-1500ms (page needs to render)
- After visual changes the viewer needs to absorb: 1500-2500ms
- Simple waits or transitions: 500-1000ms

The renderer extends each segment to `max(audio_duration, pause_after_ms)`,
so narration length also affects how long a frame stays on screen.

---

**Output**: You may summarize your convention survey in prose first,
but your response must END with exactly ONE fenced ```json block
containing every input scene `id` exactly once — no new scenes, no
splits, no omissions:

```json
{
  "scenes": [
    {
      "id": "s1",
      "action": "goto",
      "url": "http://localhost:8000/active",
      "wait_for": ["h1:has-text(\"Active Sessions\")", "main a[href*='/sessions/']"],
      "pause_after_ms": 1200,
      "notes": "SSE page — wait on the heading, never networkidle."
    },
    {
      "id": "s2",
      "action": "click",
      "selector": ["a[href=\"/active\"]", "nav a:has-text(\"Active\")"],
      "pause_after_ms": 1000
    }
  ]
}
```

- `selector` and `wait_for` are ALWAYS arrays: your best selector
  first, then 1-2 fallbacks (the renderer tries them in order — this
  is its recovery path). Notes are for fragility commentary only,
  not for stashing alternative selectors.
- Include only the fields that apply to the scene's action.
- Do NOT include `narration` or `title` — they are already canonical
  in the storyboard and you must not re-type them.
