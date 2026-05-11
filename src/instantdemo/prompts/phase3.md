For each segment in the narrative above, find the implementation details
needed to render the demo against the live app. Use both sources of
truth:

1. **The live app** — use `curl` (via `Bash`) or `WebFetch` to fetch the
   actual rendered HTML for each route the demo visits. This is the
   authoritative source for selectors and labels. The DOM you see in
   `curl http://localhost:PORT/route` is what Playwright will see when
   it renders.

2. **The frontend source** (components, routes, layouts) — fills in
   gaps when the rendered HTML is dynamic (data-testid attributes may
   be in JSX but not visible in initial curl output) or when you need
   to understand client-side routing.

Always reconcile the two — the source might say a nav link reads
"Active Sessions" but the rendered app might actually show "Active".
Trust the live app for what the user will see. Source code is for
context.

**Selectors** (in order of preference):
1. `data-testid` attributes — most stable
2. `aria-label` or `role` attributes — semantic and stable
3. Semantic HTML (`button[type='submit']`, `a[href*='/dashboard']`) — usually stable
4. Avoid: generated class names (`.css-1a2b3c`, `.MuiButton-root`)

When the same element can be matched several ways, prefer the most stable.

**Wait conditions**:
- For `goto` / `navigate`, what indicates the page is ready? An element
  appearing? An API response rendering?
- For pages with SSE or WebSockets, use `wait_for` with a selector — never
  rely on `networkidle` (it never resolves with persistent connections).

**Actions**: The rendering pipeline uses Playwright. Actions map to
Playwright `page` methods. Use whichever fits the interaction:
- `goto` or `navigate` — load a URL
- `click` — click an element
- `fill` — type into an input
- `hover` — hover over an element
- `scroll` — scroll the page viewport (`window.scrollBy`)
- `evaluate` — run arbitrary JavaScript (useful for in-container scrolls
  via `document.querySelector(...).scrollBy(...)`)
- `wait` — no action, narration plays over a static frame
- Any other Playwright `page` method works (`select_option`, `press`,
  `check`, etc.)

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

**Output**: Reproduce each segment from the narrative, augmenting it
with the resolved technical details. Use this format per segment:

```
### Segment N — [title]
- **Action:** <goto | click | fill | hover | scroll | evaluate | wait | ...>
- **Narration:** "[narration text]"   (or "(silent)")
- **URL:** http://...                  (goto only)
- **Selector:** <CSS selector>          (click / fill / hover)
- **wait_for:** <selector>              (optional, mainly for goto)
- **Value:** <text>                     (fill only)
- **Pixels:** <integer>                 (scroll only)
- **Expression:** <JS expression>       (evaluate only)
- **pause_after_ms:** <integer>
- **Notes:** <optional — selector fragility, alternatives, etc.>
```

Include only the lines that apply to the segment's action. Number the
segments to match the narrative input.
