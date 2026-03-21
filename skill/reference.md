# Demo Script Reference

## Rendering Engine

The rendering pipeline (`render.py`) uses **Playwright** for browser automation and video capture. Actions in the script map to Playwright `page` methods. Selectors use Playwright's selector syntax:

- CSS selectors: `a[href*='/sessions/']`, `input[name='email']`, `.card:first-child`
- Data attributes: `[data-testid='submit-button']`
- Text selectors: `text=Sign up`
- ARIA: `role=button[name='Submit']`

Prefer `data-testid` or semantic HTML for stability. Avoid generated class names (e.g., `.css-1a2b3c`).

## JSON Schema

### Top-level fields

| Field | Type | Required | Description |
|---|---|---|---|
| `title` | string | No | Display name for the demo (currently informational only) |
| `resolution` | object | Yes | Viewport size: `{ "width": 1280, "height": 720 }` |
| `segments` | array | Yes | Ordered list of narration + action pairs |

### Segment fields

Every segment has these common fields:

| Field | Type | Required | Description |
|---|---|---|---|
| `narration` | string | Yes | Text spoken by TTS. Can be empty string for silent segments. |
| `action` | string | Yes | Playwright `page` method name (see Actions below) |
| `pause_after_ms` | number | No | Minimum time (ms) to stay on this segment. Actual duration = `max(audio_duration, pause_after_ms)`. Default: 0. |

Additional fields depend on the action (see below). Any extra fields in the segment are passed as arguments to the Playwright method.

### Actions

Actions are **open-ended** — any valid Playwright `page` method works. Common actions:

#### `goto` (navigate to a URL)

| Field | Type | Required | Description |
|---|---|---|---|
| `url` | string | Yes | The URL to navigate to |
| `wait_for` | string | No | CSS selector to wait for after navigation (15s timeout). Use this instead of `networkidle` for pages with SSE/websockets. |

```json
{
  "narration": "Open the dashboard.",
  "action": "goto",
  "url": "http://localhost:3000/dashboard",
  "wait_for": "[data-testid='dashboard-loaded']",
  "pause_after_ms": 1500
}
```

**Note:** The existing example script uses `"action": "navigate"` which render.py maps to `page.goto()`. Both `goto` and `navigate` work.

#### `click` (click an element)

| Field | Type | Required | Description |
|---|---|---|---|
| `selector` | string | Yes | Playwright selector for the element to click (10s timeout) |

```json
{
  "narration": "Click the Create Project button.",
  "action": "click",
  "selector": "[data-testid='create-project']",
  "pause_after_ms": 1500
}
```

#### `fill` (type text into an input)

| Field | Type | Required | Description |
|---|---|---|---|
| `selector` | string | Yes | Playwright selector for the input element |
| `value` | string | Yes | Text to type |

```json
{
  "narration": "Enter your email address.",
  "action": "fill",
  "selector": "input[name='email']",
  "value": "demo@example.com",
  "pause_after_ms": 1000
}
```

#### `hover` (hover over an element)

| Field | Type | Required | Description |
|---|---|---|---|
| `selector` | string | Yes | Playwright selector for the element |

```json
{
  "narration": "Hover over the chart to see details.",
  "action": "hover",
  "selector": ".chart-container",
  "pause_after_ms": 2000
}
```

#### `scroll` (scroll the viewport)

| Field | Type | Required | Description |
|---|---|---|---|
| `pixels` | number | Yes | Pixels to scroll vertically (positive = down) |

```json
{
  "narration": "Scroll down to see more results.",
  "action": "scroll",
  "pixels": 400,
  "pause_after_ms": 1500
}
```

#### `wait` (no browser action — narration only)

No additional fields. The browser stays on the current page while narration plays.

```json
{
  "narration": "The dashboard updates in real time as new data arrives.",
  "action": "wait",
  "pause_after_ms": 2500
}
```

#### Other Playwright methods

Any `page` method can be used. For example:

- `select_option` — select from a dropdown: `{ "action": "select_option", "selector": "#country", "value": "US" }`
- `press` — press a keyboard key: `{ "action": "press", "selector": "input", "key": "Enter" }`
- `check` — check a checkbox: `{ "action": "check", "selector": "#agree-terms" }`

Consult the [Playwright Page API](https://playwright.dev/python/docs/api/class-page) for the full list.

## Annotated Example

From the Active Sessions demo of claude-code-analytics:

```json
{
  "title": "Active Sessions Demo",
  "resolution": { "width": 1280, "height": 720 },
  "segments": [
    {
      // Segment 1: Navigate to the page. wait_for ensures cards are loaded
      // before narration begins (SSE page — can't use networkidle).
      "narration": "Claude Code Analytics gives you a live view of all your running Claude Code sessions.",
      "action": "navigate",
      "url": "http://localhost:5173/active",
      "wait_for": "a[href*='/sessions/']",
      "pause_after_ms": 1000
    },
    {
      // Segment 2: No action — just narrate while the user absorbs the page.
      // 2000ms pause gives breathing room after navigation.
      "narration": "Each card shows the project name, how long the session has been running, and recent messages.",
      "action": "wait",
      "pause_after_ms": 2000
    },
    {
      // Segment 3: Click a session card. The selector targets any session link.
      // Playwright clicks the first match.
      "narration": "Click any card to jump straight into the conversation viewer for that session.",
      "action": "click",
      "selector": "a[href*='/sessions/']",
      "pause_after_ms": 1500
    },
    {
      // Segment 4: Let the user absorb the session detail page.
      "narration": "Here you can see the full conversation with messages, tool uses, and token stats.",
      "action": "wait",
      "pause_after_ms": 2000
    }
  ]
}
```

**Why 4 segments**: This demo covers one flow (list → detail) in ~30 seconds. Short enough to hold attention, long enough to show value.

**Why these pause values**: Navigation gets 1000ms (page needs to render). Wait segments get 2000ms (viewer needs time to read). Click gets 1500ms (enough for the transition animation).

## Common Patterns

### SSE / WebSocket pages

Playwright's `networkidle` wait state never resolves on pages with persistent connections (SSE, WebSockets, long-polling). Always use:

```json
{
  "action": "goto",
  "url": "http://localhost:3000/live",
  "wait_for": "[data-testid='content-loaded']"
}
```

The `wait_for` field waits for a specific element to appear (15s timeout), which is reliable regardless of network activity.

### Auth bypass for local dev

If the app has auth, check for dev-mode bypass. Common patterns:
- `.env` with `AUTH_DISABLED=true`
- Dev credentials in `.env.example` or README
- Auto-login on localhost

If auth is required, add a login segment at the start:

```json
[
  { "action": "goto", "url": "http://localhost:3000/login", "narration": "", "pause_after_ms": 500 },
  { "action": "fill", "selector": "input[name='email']", "value": "demo@example.com", "narration": "", "pause_after_ms": 300 },
  { "action": "fill", "selector": "input[name='password']", "value": "password", "narration": "", "pause_after_ms": 300 },
  { "action": "click", "selector": "button[type='submit']", "narration": "Let's sign in and take a look around.", "pause_after_ms": 1500 }
]
```

Empty `narration` on setup segments keeps them silent — narration starts when the interesting part begins.

### Scroll then wait (lazy loading)

For pages that lazy-load content on scroll:

```json
[
  { "action": "scroll", "pixels": 600, "narration": "Scroll down to see the analytics section.", "pause_after_ms": 500 },
  { "action": "wait", "narration": "Charts load automatically as you scroll.", "pause_after_ms": 2000 }
]
```

Split into two segments so the narration about loaded content plays after the content appears.

## Narration Guide

These are **recommended defaults** — override them based on the user's preferences for tone, audience, and style.

**Default style:**
- Short sentences — under 15 words each
- Present tense — "Click the button" not "You would click the button"
- Spoken word — contractions are fine ("Here's" not "Here is"), avoid written-English constructions
- No jargon — "shows your running sessions" not "renders the active session state"
- Match narration length to visual pacing — don't narrate for 10 seconds while nothing changes on screen

**Ask the user about:**
- Tone: casual (dev advocate) vs. formal (enterprise sales)
- Audience: technical (developers) vs. non-technical (end users, execs)
- Terminology: does the product have specific names for features?
- Branding: should the product name be mentioned? How?

**Empty narration**: Use `"narration": ""` for setup segments (login, scrolling to position) where silence is appropriate.
