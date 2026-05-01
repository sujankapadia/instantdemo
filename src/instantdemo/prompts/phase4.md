Translate the technical plan above into a `demo-script.json` file that
the renderer can consume. Use the schema below.

## Top-level structure

```json
{
  "title": "Demo Title",
  "resolution": { "width": 1280, "height": 720 },
  "segments": [
    /* one object per segment */
  ]
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `title` | string | No | Display name (informational). Pull from the narrative title. |
| `resolution` | object | Yes | Always `{ "width": 1280, "height": 720 }` unless told otherwise. |
| `segments` | array | Yes | Ordered list of segment objects. |

## Common segment fields (every segment)

| Field | Type | Required | Description |
|---|---|---|---|
| `narration` | string | Yes | TTS text. Use `""` for silent segments. |
| `action` | string | Yes | Playwright `page` method name (see below). |
| `pause_after_ms` | number | No | Minimum dwell time. Final duration = `max(audio_duration, pause_after_ms)`. |

## Per-action fields

| Action | Required | Optional | Notes |
|---|---|---|---|
| `goto` (alias `navigate`) | `url` | `wait_for` | `wait_for` is a CSS selector; use it for SSE/SPA pages instead of `networkidle`. |
| `click` | `selector` | — | First match wins (10s timeout). |
| `fill` | `selector`, `value` | — | Sets input text. |
| `hover` | `selector` | — | — |
| `scroll` | `pixels` | — | Scrolls the page viewport (`window.scrollBy(0, pixels)`). For in-container scroll, use `evaluate`. |
| `evaluate` | `expression` | — | Runs arbitrary JavaScript. Useful for in-container scrolls. |
| `wait` | — | — | No browser action; narration plays over the static frame. |
| Other (`select_option`, `press`, `check`, ...) | varies | varies | Any Playwright `page` method works; extra fields pass through as kwargs. |

## Worked example (small)

```json
{
  "title": "Active Sessions Demo",
  "resolution": { "width": 1280, "height": 720 },
  "segments": [
    {
      "narration": "Claude Code Analytics gives you a live view of running sessions.",
      "action": "goto",
      "url": "http://localhost:8000/active",
      "wait_for": "a[href*='/sessions/']",
      "pause_after_ms": 1000
    },
    {
      "narration": "Each card shows the project, duration, and recent messages.",
      "action": "wait",
      "pause_after_ms": 2000
    },
    {
      "narration": "Click any card to open the conversation viewer.",
      "action": "click",
      "selector": "a[href*='/sessions/']",
      "pause_after_ms": 1500
    }
  ]
}
```

## JSON quoting gotcha for `evaluate`

The `expression` value lives inside a JSON string, so its inner quotes
have to play nicely:

- Prefer unquoted attribute selectors: `[data-testid=conversation-scroll]`
- Or escape double quotes: `[data-testid=\"conversation-scroll\"]`
- Avoid single quotes around attribute values — they work in JavaScript
  but produce noisy nested-quoting in JSON.

## Translation rules

- **One JSON segment per technical-plan segment.** If the plan expands a
  step into sub-steps (e.g. "9a / 9b / 9c / 9d" for a multi-step dialog),
  flatten them into consecutive JSON segments. Re-number is fine — the
  renderer doesn't care about segment numbers, only order.
- **Field name mapping**: the plan uses Title-Case headings (`Selector`,
  `wait_for`, `Pixels`, `Expression`, `pause_after_ms`). The JSON uses
  lowercase: `selector`, `wait_for`, `pixels`, `expression`, `pause_after_ms`.
- **Skip irrelevant fields**: only include fields that apply to the
  segment's action (don't add `selector` to a `wait` segment, etc.).
- **Notes from the plan stay out of the JSON.** Those are for human
  reviewers, not the renderer.
- **Narration**: copy verbatim from the plan. If the plan says "(silent)",
  use an empty string `""`.

Use the Write tool to write the JSON to the path the user specified.
