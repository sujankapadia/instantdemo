Validate the demo script against the live app and decide whether
rendering should proceed.

You have read access to the script and Bash access for `curl` and
`python` (for a Playwright probe).

Run these checks:

1. **URL reachability** — for each segment with action `goto` or
   `navigate`, `curl` the URL and check the HTTP status. 200/300 are
   fine; 400+ is a problem.

2. **Selector existence** — for each segment whose action requires a
   selector (`click`, `hover`, `fill`, `check`, `select_option`, etc.),
   verify the selector becomes available on the relevant page. Use a
   Playwright probe via `python -c` (or write a temp script and run it).

   **Use `page.wait_for_selector(selector, timeout=10000)`, not
   `page.query_selector(selector)`.** The renderer itself uses
   `wait_for_selector` with a timeout — your probe should mirror that
   behavior. SPA pages routinely populate their DOM via SSE / fetch /
   lazy loading after the initial route mount; a `query_selector`
   returning `None` doesn't mean the selector is missing, just that it
   isn't there *yet*. A `wait_for_selector` that times out after 10s
   is what genuine missing means.

   Walk through the script in order so each page is visited via the
   same navigation path the renderer will use (otherwise SPA-only
   selectors won't be reachable).

3. **`wait_for` selectors** — if a segment has a `wait_for` field, also
   verify that selector resolves (again, with `wait_for_selector`, not
   `query_selector`) on the destination page.

Probe scripts should be small and conservative:
   - 15-second timeout per page load
   - Don't try every segment exhaustively if the same page is visited
     repeatedly — group by page
   - Don't run the actual narration / TTS / video recording here; only
     `query_selector` checks

## Output format

Write a concise markdown report with one row per segment showing PASS,
WARN, or FAIL plus a one-line note. Group by page where it makes the
report cleaner.

End the report with **exactly one** of these directive lines on its own
line, no extra text on that line:

    RENDER_OK
    RENDER_BLOCKED: <one-sentence reason>

Pick `RENDER_BLOCKED` only when the issues are bad enough that a render
is guaranteed to fail or produce a broken video. Examples:

- A `goto` URL is unreachable (the user's app isn't running)
- The very first selector in the flow doesn't exist (renderer will
  abort on the first action)
- The render dependencies clearly aren't installed

Use `RENDER_OK` if there are missing-but-non-critical selectors (e.g.
the bookmark-creation flow can't find a target message because the
page is empty — the demo will still produce a video, just an
unimpressive one). Note the warnings; don't block.

**Do not run the renderer yourself.** The CLI handles that after
reading your directive.
