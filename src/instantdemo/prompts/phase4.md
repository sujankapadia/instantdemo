Run a full end-to-end dress rehearsal of the demo against the live app.

Phase 3 produced a per-segment plan with selectors derived from
source code. Your job is to **walk every segment in sequence as
the renderer will**, observe what actually happens at each step,
and refine the plan so the recording in Phase 6 plays back
cleanly. You are NOT redoing source analysis — Phase 3's plan is
the starting hypothesis.

You have `Read` (to consult Phase 3's plan, prior phase artifacts,
and — sparingly — source for context) and `Bash` (to write a
Playwright rehearsal script via heredoc and run it). You do NOT
have Write — Phase 5 (Build) emits the JSON.

### Inputs

- The Phase 3 plan is at the path noted above. Read it first.
- The app is running at the URL noted above.
- The user's intent (audience, tone, length, focus, excludes, addenda)
  is in `intent.json` if it exists — read it. Any narration changes
  you make must stay within these constraints.

### Workflow

1. **Write one end-to-end rehearsal script** that walks every
   segment in order, exactly as the renderer in Phase 6 will.

   Use `sync_playwright`. For each segment, perform the segment's
   action against the segment's selector, observe the result, then
   advance to the next. Do NOT group segments by page or probe
   pages independently — the value of the rehearsal is observing
   what happens *between* segments (transitions, layout shifts,
   redirects, state changes that affect later selectors).

   The script should print observations as it goes — JSON-per-line
   to stdout is fine. For each segment capture:

   - `index` (1-based)
   - `action` (the action attempted)
   - `selector_attempted` (Phase 3's primary)
   - `selector_resolved` (may differ if a fallback was used)
   - `wait_outcome` — e.g., `resolved_in_1200ms` or
     `timeout_after_10s`
   - `post_action_state`:
     - `url` (current `page.url`)
     - `title` (current `page.title()`)
     - `console_errors` (any console errors logged since last
       segment — register a handler at script start)
     - `key_elements` — narrative-relevant content the next
       segment or narration claim references. For example, if
       the narrative says "the running sessions list", record
       how many items resolve. This is the data narration
       regrounding will use.
   - `timing_ms` — observed action-to-DOM-settled time

   Use `page.wait_for_selector(selector, timeout=10000)`, never
   `query_selector`. SPA pages populate the DOM via SSE / fetch
   / lazy loading; a synchronous `query_selector` returning None
   doesn't mean missing, just "not yet". A 10s
   `wait_for_selector` timeout is what genuine missing looks
   like.

   **Never use a wait_for that targets an `<option>` element** (or
   anything else inside a closed `<select>`): Playwright's
   visibility model treats them as hidden, so the renderer's
   visible-wait can never resolve — even if your rehearsal read
   them successfully. Wait on a visible consequence instead (a
   count label, a list item, the select element itself).

   **Rehearsal screenshots (REQUIRED — these become the storyboard
   thumbnails the user reviews):** immediately after each segment's
   action settles (its wait resolved and the page is showing what
   the narration describes), save:

   ```python
   page.screenshot(path=f"{rehearsal_dir}/{scene_id}.png")
   ```

   One PNG per segment, named by the segment's scene id exactly as
   listed in the plan (`s1.png`, `s7.png`, `s12.png`, ...) — use
   the id shown for each segment, NOT its position in the list.
   Save them on every rehearsal pass — later iterations overwrite
   earlier files, which is correct (the final passing rehearsal's
   screens are what the user should see). They also stream live to
   the user as you work.

   **Progress log (live "what's happening now"):** the user watches
   a header sentence while you work, and a screenshot only appears
   once a scene is reached — so also APPEND one line per step to
   `{rehearsal_dir}/progress.log`, flushing after each write
   (`open(..., "a")` then `f.write(line); f.flush()`):

   - after each segment's action settles, append `scene <scene_id>`
     (e.g. `scene s7`)

   This is best-effort telemetry, not part of your findings — if a
   step is awkward to log, skip it; never let logging change what
   you rehearse.

2. **Apply Phase 3's listed fallbacks when the primary fails.**
   Phase 3 lists 1-2 fallbacks per segment in the Notes line.
   If the primary's `wait_for_selector` times out, try each
   fallback in order. If one resolves, swap it in as the new
   primary and continue.

3. **Read the trace and decide what to revise.** You have three
   levels of authority (see "Authority levels" below). Apply
   the revisions in your output. If issues exceed your authority,
   surface as FAIL_* with a humanized suggestion (per "Suggestion
   rules" below).

4. **Re-run the rehearsal if needed.** You may run the script
   up to 3 times total (the runner enforces this). If a revision
   resolves the issue, the next rehearsal should observe a clean
   pass. If the same failures recur across iterations, mark them
   FAIL and stop — re-running won't help.

5. **Rehearsal scripts are throwaway**. The recording in Phase 6
   is independent. Keep the script focused: walk segments, print
   observations, exit cleanly.

### Authority levels — what you can revise

**Level 1 — Mechanical (no narration changes).** Always allowed.

- Selector swap when the primary fails and a Phase 3 fallback
  works — record as PASS with `selector_swapped: true`
- Timing adjustment: increase `pause_after_ms` if you observed
  the next action's `wait_for` racing against the previous
  action's effect
- Wait-condition refinement: replace `wait_for: domcontentloaded`
  with a specific selector when the page renders async, etc.

**Level 2 — Narration regrounding.** Allowed within the user's
`intent` constraints.

When you observe that the narration's specific claims don't
match the live state — e.g., the narrative says "5 active
sessions" and you observed 2 — rewrite the narration to match
what was observed.

Rules:
- Stay within the segment's *intent* (same purpose, same beat
  in the demo flow)
- Stay within the user's `intent.json` constraints — preserve
  audience (technical vs non-technical), tone (casual vs formal),
  length (don't expand a short narration into a long one or
  vice versa), and never re-introduce material the user listed
  in `intent.excludes`
- Drop overclaim, don't replace it with a different overclaim.
  "5 active sessions" observed as 2 → rewrite as "the active
  sessions list" or "each session that's currently running",
  not "2 active sessions" (the count will be different at
  recording time)
- When in doubt, drop the specific claim — a shorter accurate
  narration beats a longer embellished one

Record narration changes as PASS with:
- `narration_revised: true`
- `narration_from: <original>`
- `narration_to: <replacement>`

**Level 3 — Structural changes. NOT in your authority.**

The following stay BLOCKED with a humanized suggestion:
- Dropping a segment that has nothing to show
- Adding a segment to cover a transition
- Reordering segments
- Changing the demo's overall arc

If you observe one of these is needed, mark the relevant
segment FAIL_NARRATIVE (when the issue is "the narrative
references something not present") or FAIL_SELECTOR (when no
element exists for the segment to operate on), with a
suggestion telling the user what to do (e.g., "Open Regenerate
and add 'X' to the Exclude field"). The runner halts; the
user makes the structural call.

### Output

Your response must END with exactly ONE fenced JSON findings
block — that block is the entire contract. The runner applies
your revisions to the canonical plan and renders the human
report from it; do NOT write a per-segment markdown report.
You may summarize observations in prose before the block.

```json
{
  "summary": {
    "total": <total segment count>,
    "pass": <count of PASS segments>,
    "fail_selector": <count of FAIL_SELECTOR segments>,
    "fail_narrative": <count of FAIL_NARRATIVE segments>,
    "warn": <count of WARN segments>,
    "overall": "OK" | "BLOCKED"
  },
  "segments": [
    {
      "index": <segment number, 1-based>,
      "status": "PASS" | "FAIL_SELECTOR" | "FAIL_NARRATIVE" | "WARN",
      "reason": "<technical observation — what you found on the live app, written for a developer reviewing the report>",
      "note_for_user": "<for WARN and FAIL_*: ONE plain sentence for the demo's maker — what this means for their film and what you did about it. First person, no engineering vocabulary (no selectors, waits, pixels, DOM). Example: \"Every export file holds exactly 100 notes, so I dropped the line about the count changing each time.\" Omit for PASS.>",
      "suggestion": "<for FAIL_*: USER-FACING fix — see Suggestion rules below; omit for PASS/WARN>",
      "selector_swapped": <true if you replaced Phase 3's primary; omit if not>,
      "from": "<Phase 3's original primary; only when selector_swapped>",
      "to": "<your replacement; only when selector_swapped>",
      "narration_revised": <true if you regrounded narration; omit if not>,
      "narration_from": "<original narration; only when narration_revised>",
      "narration_to": "<replacement narration; only when narration_revised>",
      "updates": {
        "wait_for": ["<refined wait selector>", "<fallback>"],
        "pause_after_ms": <adjusted pacing>
      }
    }
  ]
}
```

**The `updates` object (Level 1 refinements):** if the rehearsal
led you to adjust a segment's wait condition or pacing, record it
here — this is the ONLY way those changes reach the renderer.
Include only the keys you actually changed; omit `updates`
entirely when nothing changed. Worked example: you observed that
segment 3's detail pane populates only after `#note-title`
contains text, and the page needs 2s (not 1s) to settle:

```json
{"index": 3, "status": "PASS", "reason": "detail pane populates ~1.4s after click",
 "updates": {"wait_for": ["#note-title:has-text(\"Marketing\")"], "pause_after_ms": 2000}}
```

**Status rules:**

- `PASS`: the rehearsal walked through this segment cleanly —
  the selector resolved, the action succeeded, and the narration
  (after any regrounding) matches what was observed. A successful
  selector swap (PASS + `selector_swapped: true`) or narration
  regrounding (PASS + `narration_revised: true`) is still PASS.
  These are fixes within your authority, not warnings.
- `FAIL_SELECTOR`: the selector doesn't resolve on the live app
  (10s `wait_for_selector` timeout, all Phase 3 fallbacks tried).
  Or: an earlier segment's action broke a later segment's
  selector (state changed in a way Phase 3 couldn't predict).
- `FAIL_NARRATIVE`: the selector resolves but the resolved
  element doesn't match the narrative, and the mismatch can't
  be fixed by regrounding alone — e.g., the narrative references
  a feature that's broken on the live app, or content that
  doesn't exist for structural reasons (no seed data, wrong
  page state).
- `WARN`: works but the user should know — flaky timing,
  borderline selector, intermittent console errors that didn't
  break execution. Reserved for genuine concerns; not for "I
  had to swap a selector" or "I rewrote the narration" (those
  are PASS).

**Suggestion rules** (`suggestion` field, FAIL_* only):

The `suggestion` text is shown verbatim to a non-technical user
in the GUI. Write it for that audience:

- Describe what the user should DO, in plain language. Avoid
  internal terms like "segment", "selector", "wait_for",
  "narrate", "DOM", or specific CSS / Playwright syntax. The
  technical detail belongs in `reason`, not `suggestion`.
- Frame fixes in terms of the GUI actions actually available:
  - **Seed data**: "Run the app long enough for X to appear",
    "Create a Y in the app, then regenerate."
  - **Adjust the intent / scope**: "Open Regenerate and add
    'Recently ended sessions' to the Exclude field so the demo
    skips that part."
  - **Reword the goal**: "Open Regenerate and rewrite the goal
    to focus on the parts of the app you want to show, without
    referencing X."
- One short paragraph, two sentences max. No bullet lists, no
  code. The triage panel shows this text directly.

Example contrast:

- **Bad** (developer-y): "Drop Segment 6 from the demo and
  re-narrate Segment 7 to bridge to the click-through. The
  scrollBy is a no-op since scrollHeight=clientHeight."
- **Good** (user-facing): "The 'Recently ended sessions' part
  of the demo can't be shown because none ended in the last 2
  hours. Either wait for one to end (or end one yourself),
  then regenerate; or open Regenerate and add 'Recently ended
  sessions' to the Exclude field so the demo skips that part."

**Overall rules:**

- `BLOCKED` if `fail_selector + fail_narrative >= 1`.
- `OK` otherwise (all PASS / WARN).

There is no PARTIAL outcome. The pipeline either has all the
information it needs to produce a real demo, or it doesn't and
the user needs to address the failures before continuing.
