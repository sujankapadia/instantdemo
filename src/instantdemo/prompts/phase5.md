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
| `action` | string | Yes | One of the actions in the table below — this set is closed; no other values are accepted. |
| `pause_after_ms` | number | No | Minimum dwell time. Final duration = `max(audio_duration, pause_after_ms)`. |

## Per-action fields

| Action | Required | Optional | Notes |
|---|---|---|---|
| `goto` (alias `navigate`) | `url` | `wait_for` | `wait_for` is a CSS selector or array of CSS selectors (see Fallbacks below). Use for SSE/SPA pages instead of `networkidle`. |
| `click` | `selector` | — | `selector` may be a string OR array (fallbacks tried in order). |
| `fill` | `selector`, `value` | — | Sets input text. `selector` accepts fallback array. |
| `hover` | `selector` | — | `selector` accepts fallback array. |
| `scroll` | `pixels` | — | Scrolls the page viewport (`window.scrollBy(0, pixels)`). For in-container scroll, use `evaluate`. |
| `evaluate` | `expression` | — | Runs arbitrary JavaScript. Useful for in-container scrolls. |
| `wait` | — | — | No browser action; narration plays over the static frame. There is no wait-for-selector action — if a segment needs a readiness condition, the preceding action's behavior (click result, goto `wait_for`) must provide it. |
| `select_option` | `selector`, `value` | — | Selects an option in a `<select>`. |
| `press` | `selector`, `key` | — | Presses a key on the focused element. |
| `check` / `uncheck` | `selector` | — | Toggles a checkbox. |

These are the ONLY valid actions. Do not invent new action names
(e.g. Playwright method names like `wait_for_selector`) — the
renderer rejects unknown actions and the script will fail validation.

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

## Fallback selectors

Phase 3 often lists fallback selectors in segment Notes (e.g.
`Fallbacks: a[href="/active"], main a:first-child`). Carry them
forward into the JSON.

- **`selector`** (click / fill / hover / press / check / etc.):
  emit as a JSON array when fallbacks exist, primary first.
- **`wait_for`** (goto / navigate): same — JSON array when
  fallbacks exist.
- When no fallbacks are listed, keep emitting a single string.
  Both forms are valid and the renderer normalizes them.

Example with fallbacks:

```json
{
  "narration": "Open the active sessions page.",
  "action": "click",
  "selector": ["a[href=\"/active\"]", "nav a:has-text(\"Active\")", "[data-testid=\"nav-active\"]"],
  "pause_after_ms": 1000
}
```

The renderer tries each selector in order with a per-candidate
timeout (total budget ~10s for actions, ~15s for `wait_for`).
First match wins.

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
