Verify the Phase 3 hypothesis against the live application.

Phase 3 produced a per-segment plan with selectors derived from
source code. Your job is to confirm each selector actually resolves
on the running app, and to apply Phase 3's listed fallbacks when
the primary fails. You are NOT redoing source analysis — Phase 3's
plan is the starting point. Your contribution is the live-verification
layer.

You have `Read` (to consult Phase 3's plan and, sparingly, source
for context) and `Bash` (to write a Playwright probe via heredoc
and run it). You do NOT have Write — Phase 5 (Build) emits the JSON.

### Inputs

- The Phase 3 plan is at the path noted above. Read it first.
- The app is running at the URL noted above.

### Workflow

1. **Group segments by page**. A flow that visits 2 routes with 5
   click targets is 2 page loads, not 7. Plan one probe per page.

2. **Probe each page once**. Write a small Python script using
   `sync_playwright`, run it via `bash`. The probe should:
   - Navigate to the page (same nav path the renderer will use —
     `goto` for the first page, then click links for SPA hops)
   - For each segment that lives on this page, call
     `page.wait_for_selector(selector, timeout=10000)`
   - Print PASS/FAIL plus the resolved selector for each

   Use `wait_for_selector`, never `query_selector`. SPA pages
   populate the DOM via SSE / fetch / lazy loading after route
   mount; a synchronous `query_selector` returning None doesn't
   mean missing, just "not yet". A 10s `wait_for_selector` timeout
   is what genuine missing looks like.

3. **Narrative alignment — not just selector validity.** A selector
   that resolves to *some* element isn't enough — the element has
   to match what the narrative is asking for. For each segment,
   ask: does the element this selector resolves to actually have
   the properties or content the narrative describes?

   When the narrative specifies content properties — an item with
   a specific label or state, a row matching some condition, a
   card containing particular content — verify the resolved
   element exhibits those properties on the live app. If it
   doesn't, refine the selector by combining the structural
   target with a content predicate (Playwright's `:has(...)` and
   `:has-text("...")` are the typical tools), or report the
   mismatch with a plain-English recommendation. Don't fabricate
   predicates the source doesn't support.

4. **When the primary fails**, try the fallbacks Phase 3 listed
   in the segment's Notes line. If one of them resolves, swap it
   in as the new primary in your output. If they all fail, mark
   the segment FAIL and recommend in plain English what would
   fix it (e.g. "no card with the described content visible —
   seed data may be missing").

5. **Probe scripts are throwaway**. Keep them small. Group by
   page. Don't probe the same page twice.

### Output

Reply with a markdown report mirroring the Phase 3 segment
structure, with each segment showing the **verified** primary
selector and a one-line note on the probe result. (Your response
text is the report — the runner saves it to `phase4.md`. Don't
call any Write tool; you don't have one.)

```
### Segment N — [title]
- **Action:** <unchanged>
- **Narration:** "[unchanged]"
- **URL:** <unchanged for goto>
- **Selector:** <verified selector — may be the original or a
  Phase 3 fallback that was swapped in>
- **wait_for:** <verified>
- **pause_after_ms:** <unchanged>
- **Verified:** PASS | FAIL — <one-line probe observation>
- **Notes:** <retained from Phase 3; add live-data observations
  here if relevant>
```

End the report with a one-line summary:

    EXPLORE_OK — N segments verified
    EXPLORE_PARTIAL — N PASS, M FAIL; Phase 5 will see flagged segments
    EXPLORE_BLOCKED — <one-sentence reason>

`EXPLORE_BLOCKED` is for catastrophic problems (app is down, every
selector misses). Otherwise, prefer `EXPLORE_PARTIAL` and let Phase
5 carry forward what's verified — the user iterates via Regenerate.
