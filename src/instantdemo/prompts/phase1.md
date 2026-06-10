You are analyzing a RUNNING web application at {url} to understand
what it does and how it works. Build your understanding primarily by
observing and driving the live app with headless Playwright (Python)
scripts run via Bash — the live app is the ground truth.

## Exploration steps

1. **Load the start page**: capture the page title, main headings,
   navigation links, and visible copy.
2. **Enumerate the screens**: follow each navigation link (and any
   obvious routes you discover along the way). For each screen,
   record its URL, what it's for, and the main UI regions — lists,
   tables, charts, forms, buttons, search boxes.
3. **Go deep on demo-relevant screens**: for the screens a demo
   would showcase, observe what data is displayed and what's
   clickable. Follow one representative click-through (e.g. open a
   list item) to see where it leads.
4. **Note access details**: port, any login or auth wall, anything
   that must be true before a demo (data that must exist, services
   that must be running).

## Screenshots (important — these stream live to the user)

For EVERY distinct screen you visit, save a PNG to
{exploration_dir} with a sequential kebab-case name:
`001-home.png`, `002-notes-list.png`, `003-note-detail.png`, ...
Save each screenshot as soon as the screen has rendered — the user
watches them appear while you explore. This is REQUIRED, not
optional: your final JSON is validated against the saved files, and
a response whose `screens` reference no existing screenshots will be
sent back for correction. Pattern:

```python
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    page.goto("{url}", wait_until="domcontentloaded")
    page.wait_for_selector("body")
    page.screenshot(path="{exploration_dir}/001-home.png", full_page=False)
    # ... navigate, observe, screenshot each distinct screen ...
    browser.close()
```

## Safety rules (important)

- Read-only exploration. Do NOT trigger destructive or data-mutating
  controls: no delete/remove buttons, no imports or uploads, no form
  submissions. Navigation clicks, opening list items, scrolling, and
  reading are all fine.
- Pages may use Server-Sent Events or live polling: do not wait for
  `networkidle`. Use `domcontentloaded` plus `wait_for_selector`
  instead.

## Output

Summarize your findings in prose if helpful, then END your response
with exactly ONE fenced ```json block:

```json
{
  "app_model": "Markdown summary: what the app does, the main screens/features (one line each on what they render), how to access the app (port, auth, data preconditions), and demo-relevant observations.",
  "proposed_intent": {
    "goal": "One or two sentences: the demo YOU would make for this app.",
    "audience": "non-technical end users",
    "tone": null,
    "length": null,
    "focus": [],
    "excludes": [],
    "addenda": []
  },
  "screens": [
    {"name": "Notes list", "route": "/", "screenshot": "002-notes-list.png", "notes": "500 notes, search box, source filter"}
  ],
  "warnings": []
}
```

- **`proposed_intent`** is your proposal for the demo, written for
  the user to confirm or edit. If the user supplied a goal above,
  REFINE it with what you observed (name the concrete screens and
  data worth showing) — don't replace it. Lead with the payoff.
  Populate `audience` / `tone` / `length` only when you have a
  basis for them; otherwise null. Use `excludes` for things a demo
  should avoid (e.g. data-mutating buttons, screens with sensitive
  content you observed).
- **`screens`**: one entry per distinct screen you visited;
  `screenshot` is the bare filename you saved (or null);
  `route` is its path.
- **`warnings`**: anything the user should know before rendering —
  data preconditions, auth walls, volatile content, and any
  discrepancy between provided documentation and the live app.
