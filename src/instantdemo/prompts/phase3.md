For each segment in the narrative above, find the implementation details
needed to render the demo against the live app. Read the frontend source
(components, routes, layouts) to identify stable selectors and the right
wait conditions.

**Selectors — find them in the source, don't infer them.**

A file or component named `conversation-viewer.tsx` does NOT mean
the rendered element has `data-testid="conversation-viewer"`.
Component names are conventions; the rendered attribute values
are the contract Playwright sees. Always grep the source for the
actual attribute literals before committing to a selector.

Search strategies, in priority order. For each segment, try them
top-down and pick the first that yields a concrete, stable match:

1. **Test IDs** — grep for `data-testid="..."`. Don't assume
   the project uses `data-testid`; also check `data-test=`,
   `data-cy=`, `data-qa=`. Skim a few files; whichever
   convention shows up most is the one to use. If the project
   uses no test IDs at all, skip this category.

2. **ARIA / semantic attributes** — grep for `aria-label=`,
   `role=`, and accessible names. Stable across UI redesigns.

3. **Text content** — grep for the user-visible labels mentioned
   in the narrative. Useful for nav links, buttons, headings.
   Match with `:has-text("...")` or `[href="..."]` as appropriate.

4. **URLs and hrefs** — grep for `href="/..."` literals. Best for
   nav links where the destination route is more stable than the
   label text.

5. **Last resort: structural CSS** — descendant combinators on
   semantic tags (`main h1`, `nav a:first-child`). Avoid generated
   class names (`.css-1a2b3c`, `.MuiButton-root`) — they change
   on every build.

For each segment, also note one or two **fallback selectors** you
believe could work — Phase 5's validation may discover the
primary fails on the live app, and fallbacks give the recovery
path more options.

When the same element can be matched several ways, prefer the
most stable AND grep-verified one. If you can't find evidence in
the source for any of these strategies, say so explicitly in the
segment's Notes — Phase 5 will then probe the live app to fill
the gap.

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
