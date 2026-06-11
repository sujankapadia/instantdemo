# Plan: Insert Explore phase between Inspect and Build

## Context

Insert a new "Explore" phase between Inspect (today's Phase 3) and Build
(today's Phase 4). Today Phase 5 (Render) does two things: validate
selectors against the live app, then record the video. Pulling the
validation step out into its own phase between source-based planning
and JSON emission gives us:

- Tighter, single-purpose prompts per phase (better agent output)
- Phase 4 (Explore) refines selectors based on live reality before
  Phase 5 (Build) commits them to JSON. Closes the "Phase 3's hypothesis
  is wrong" failure mode that fallback propagation (#47) only partially
  addressed.
- Phase 6 (Render) becomes a strict drift-check + record, with no
  "non-critical" loophole — addresses the broken-video failure the
  latest shakedown exposed.
- Phase 4 absorbs narrative-alignment responsibility — verifying that
  the element a selector resolves to actually matches what the
  narrative is asking for, not just that the CSS is valid.

The renumbering touches Python (phases tuple, hardcoded numbers, tool
dict, server route literal), markdown filenames, and frontend constants.

After the change: Understand → Plan → Inspect → **Explore** → Build → Render.

Note: an earlier draft of this plan included a Phase 3 "match
specificity" prompt tweak. Dropped — Phase 3 sees only source, so
reasoning about narrative-specific runtime content is unreliable
there. Phase 4 (Explore) has live DOM access and is the right home
for that work. The Phase 3 prompt stays as-is.

## Approach

Two commits: backend (Python + prompts) and frontend (constants).
Intermediate states would crash, so each commit must be internally
consistent.

### Commit 1 — Insert Explore (backend)

All Python + prompt renames done in one commit; partial states would
break import chains.

**Renames (git mv to preserve blame):**
- `src/instantdemo/prompts/phase5.md` → `phase6.md`
- `src/instantdemo/prompts/phase4.md` → `phase5.md`
- `src/instantdemo/phases/validate.py` → `phases/render.py`

**New files:**
- `src/instantdemo/prompts/phase4.md` — Explore prompt (full text below)
- `src/instantdemo/phases/explore.py` — Explore phase module (skeleton below)
- `src/instantdemo/prompts/phase6.md` — new Render prompt (full text below); old phase5.md content replaced wholesale

**Edits:**

`src/instantdemo/phases/__init__.py`:
- Update `PHASES` tuple to `("analyze", "narrate", "gather", "explore", "script", "render")`
- Update `phase_artifact()` condition: `if phase_number == 4:` → `if phase_number == 5:`
  (Build moves from 4 → 5; demo-script.json is now Phase 5's output)
- Update the module docstring listing of phases

`src/instantdemo/agent_client.py` PHASE_TOOLS:
```python
PHASE_TOOLS = {
    "phase1": frozenset({"Read", "Glob", "Grep"}),
    "phase2": frozenset(),
    "phase3": frozenset({"Read", "Glob", "Grep"}),
    "phase4": frozenset({"Read", "Bash"}),       # NEW: Explore
    "phase5": frozenset({"Read", "Write"}),      # was phase4 (Build)
    "phase6": frozenset({"Read", "Bash"}),       # was phase5 (Render)
}
```

`src/instantdemo/phases/script.py` (Build, now phase 5):
- `phase_artifact(3)` → `phase_artifact(4)` (read Phase 4's verified plan, not Phase 3's hypothesis)
- `phase_artifact(4)` → `phase_artifact(5)` (write target)
- `session_id_for_phase(4)` → `session_id_for_phase(5)`
- `record_phase_result(context, 4, ...)` → `..., 5, ...`
- `summarize_run(4, ...)` → `summarize_run(5, ...)`
- Update prompt preamble: "The following is the per-segment technical plan from Phase 3" → "The following is the verified plan from Phase 4 (selectors confirmed against the live app)"

`src/instantdemo/phases/render.py` (was validate.py, now phase 6):
- `prompts.load("phase5")` → `prompts.load("phase6")`
- `session_id_for_phase(5)` → `session_id_for_phase(6)`
- `record_phase_result(context, 5, ...)` → `..., 6, ...`
- `phase_artifact(5)` → `phase_artifact(6)`
- `summarize_run(5, ...)` → `summarize_run(6, ...)`
- Update error message "Run phase 4 first" → "Run phase 5 first" (refers to upstream Build)

`src/instantdemo/cli.py`:
- `_import_phase_runner`: add `explore` dispatch; rename `validate` dispatch to `render` (import `from .phases import render`)
- `PHASES_WITH_REVIEW = (1, 2, 3, 4, 5)` — Build (now phase 5) still gets `$EDITOR` checkpoint; Phase 4 (Explore) also reviewed since its verified plan is exactly what users would want to eyeball; Phase 6 (Render) excluded (no review before final render)
- Help text and docstrings: "1..5" → "1..6", "5 phases" → "6 phases"

`src/instantdemo/server/routes/project.py`:
- `PhaseNumber = Literal[1, 2, 3, 4, 5]` → `Literal[1, 2, 3, 4, 5, 6]`
- `_artifact_path` condition: `if phase == 4:` → `if phase == 5:`
- `PathParam(..., ge=1, le=5)` → `le=6`
- Docstring: "Phases 1, 2, 3, 5 are markdown" → "Phases 1, 2, 3, 4, 6 are markdown; Phase 5 is JSON"

### Commit 2 — Frontend renumber

`frontend/src/lib/phases.ts`:
- Extend `PHASE_NAMES` to include `4: 'Explore', 5: 'Build', 6: 'Render'`
- Extend `PHASE_NAMES_ORDERED` to length 6

`frontend/src/components/PhaseRail.tsx`:
- `PHASE_NUMBERS = [1, 2, 3, 4, 5, 6] as const`

`frontend/src/components/Layout.tsx`:
- `handleNewProjectSubmit`: `phases: [1, 2, 3, 4, 5, 6]`
- Update the comment referencing "RENDER_BLOCKED in Phase 5" → "in Phase 6"

## New Phase 4 (Explore) prompt — `prompts/phase4.md`

```
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
   fix it (e.g. "no card with tool calls visible — seed data may
   be missing").

5. **Probe scripts are throwaway**. Keep them small. Group by
   page. Don't probe the same page twice.

### Output

Reply with a markdown report mirroring the Phase 3 segment
structure, with each segment showing the **verified** primary
selector and a one-line note on the probe result. (Your response
text is the report — the runner saves it to phase4.md. Don't
call any Write tool.)

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
```

The `EXPLORE_*` directives are informational for v1 — the phase runner
doesn't parse them. Future work can add machine-readable handoff if
needed.

## New Phase 6 (Render) prompt — `prompts/phase6.md`

```
Drift check the demo script against the live app, then signal whether
to render.

By this point Phase 4 (Explore) has already verified every selector
against the live app. Your job is only to confirm nothing has drifted
between Explore and now — the app could have restarted, data could
have been wiped, the user could have edited the script after Explore
ran. You are NOT re-probing every selector.

You have `Read` access to the demo script and `Bash` for `curl`
and a small Playwright smoke check.

### Checks

1. **App reachability**. `curl` the first segment's `goto` URL and
   any other distinct `goto` URLs in the script. 200/300 = fine.
   4xx/5xx or connection refused = the app isn't running.

2. **First-action smoke**. Write a small Playwright probe that
   loads the first `goto` URL and confirms the *first segment after
   goto* that requires a selector resolves via `wait_for_selector`
   (10s timeout). If the very first interactive step in the flow
   doesn't resolve, the renderer is guaranteed to abort, so we
   block here.

   Don't probe every segment. That's Explore's job and was already
   done; doing it again wastes tokens. The smoke check exists to
   catch the "Explore passed, now the app is in a different state"
   case.

### Output

Concise markdown report — a few lines is fine. End with **exactly
one** of these directive lines on its own line:

    RENDER_OK
    RENDER_BLOCKED: <one-sentence reason>

**Strict policy: any selector failure observed during this drift
check is RENDER_BLOCKED.** There is no "non-critical" loophole.
If the smoke selector resolves and the URLs are reachable, emit
`RENDER_OK`. Anything else is `RENDER_BLOCKED`. Validation already
happened upstream — by the time we're here, the bar is "is the app
still in the state Explore observed?"

Do not run the renderer yourself. The runner handles that after
reading your directive.
```

The existing `RENDER_OK` / `RENDER_BLOCKED` directive parser in
`render.py` (renamed from validate.py) keeps working unchanged.

## New `phases/explore.py` module

Mirrors the pattern from `gather.py`:

```python
"""Phase 4 — Explore the live application.

Reads the Phase 3 hypothesis plan and verifies each segment's
selectors against the running app via Playwright probes. Writes a
verified plan to `.instantdemo/phase4.md` that Phase 5 (Build)
consumes instead of the raw Phase 3 hypothesis.

Tools: Read (for phase3.md and the occasional source consult) and
Bash (for curl and a Playwright probe via python heredoc). No
Write — the agent doesn't produce JSON at this stage.
"""

from __future__ import annotations

from .. import prompts
from ..agent_client import session_id_for_phase
from . import (
    Context,
    record_phase_result,
    run_query_on_client,
    summarize_run,
)


def _build_prompt(phase3_text: str, url: str, phase3_path: str) -> str:
    template = prompts.load("phase4")
    return (
        f"The app being demoed is running at: {url}\n"
        f"The Phase 3 plan is at: {phase3_path}\n"
        "\n"
        "The following is the Phase 3 hypothesis plan. Each segment\n"
        "has a primary selector derived from source code and (often)\n"
        "fallback selectors in its Notes line.\n"
        "\n"
        "---\n"
        f"{phase3_text}\n"
        "---\n"
        "\n"
        f"{template}"
    )


async def run(context: Context) -> None:
    if context.client is None:
        raise RuntimeError(
            "Phase 4: no agent client provided in context. The CLI is "
            "responsible for creating and passing through a ClaudeSDKClient."
        )

    phase3 = context.phase_artifact(3)
    if not phase3.exists():
        raise RuntimeError(
            f"Phase 3 artifact missing at {phase3}. Run phase 3 first."
        )
    phase3_text = phase3.read_text()

    artifact = context.phase_artifact(4)
    artifact.parent.mkdir(parents=True, exist_ok=True)

    prompt = _build_prompt(phase3_text, context.url, str(phase3))
    verified_text, result = await run_query_on_client(
        context, prompt, session_id=session_id_for_phase(4)
    )

    if result is None:
        raise RuntimeError(
            "Phase 4: the Claude Agent SDK did not return a ResultMessage."
        )

    artifact.write_text(verified_text + "\n")
    record_phase_result(context, 4, result)
    print(summarize_run(4, artifact, result))
```

## Critical files to modify

**Commit 1 (backend):**
- `src/instantdemo/prompts/phase4.md` (NEW) — Explore prompt
- `src/instantdemo/prompts/phase5.md` (renamed from phase4.md) — Build prompt, content unchanged
- `src/instantdemo/prompts/phase6.md` (NEW; replaces old phase5.md) — Render prompt, leaner + strict
- `src/instantdemo/phases/__init__.py` — PHASES tuple, phase_artifact dispatch
- `src/instantdemo/phases/explore.py` (NEW) — Explore phase module
- `src/instantdemo/phases/script.py` — phase number bumps + reads phase4 not phase3
- `src/instantdemo/phases/render.py` (renamed from validate.py) — phase 5 → 6
- `src/instantdemo/agent_client.py` — PHASE_TOOLS
- `src/instantdemo/cli.py` — phase dispatch, PHASES_WITH_REVIEW
- `src/instantdemo/server/routes/project.py` — PhaseNumber literal, _artifact_path

**Commit 2 (frontend):**
- `frontend/src/lib/phases.ts` — PHASE_NAMES + PHASE_NAMES_ORDERED
- `frontend/src/components/PhaseRail.tsx` — PHASE_NUMBERS
- `frontend/src/components/Layout.tsx` — phases array, comment

## Subtle interactions

- **session_cost_totals** in `PhaseDispatcher` is keyed by session_id
  string (`"phase4"`, `"phase5"`, etc.). After renumbering, costs flow
  into the right buckets automatically. No code change.

- **segment-timing.json** is written by the renderer (`render.py`),
  keyed by segment index — unaffected.

- **GUI auto-open-on-error effect** (`Layout.tsx:113-122`) iterates
  `run.phaseUpdates` and selects the first error phase. Phase-number-
  agnostic, no code change needed.

- **Phase 5's existing prompt has fallback-array handling** (per #47)
  — Phase 4 (Explore) doesn't need to handle this. Phase 4 reads
  phase3.md (markdown with prose Notes listing fallbacks), not
  demo-script.json (which has array-form selectors). The array form
  lives strictly between Build and the renderer.

- **Existing state.json files with old shape**: pre-refactor state.json
  has phase entries keyed by "1"–"5" with old semantic meanings
  ("4" = Build, "5" = Validate). Post-refactor, "4" = Explore, "5" =
  Build, "6" = Render. Old projects loaded post-upgrade will show
  stale data under shifted keys until re-run. **No migration code in
  v1** — document in commit message, note in CHANGELOG.md if we have
  one. Real impact: only `/tmp/shakedown` and our gitignored fixtures,
  both regularly wiped.

- **Old fixture files** (`fixtures/*/.instantdemo/phase5.md`) are
  reference outputs of today's Phase 5 (validation+render decision).
  Semantically equivalent material post-refactor lives in phase4.md
  (verified plan) + phase6.md (drift check). Optional cleanup; not
  blocking.

## Verification

### Plumbing (no agent calls — cheap, deterministic)

1. Imports load: `python -c "from instantdemo.phases import analyze, narrate, gather, explore, script, render; from instantdemo.cli import _import_phase_runner; [_import_phase_runner(n) for n in range(1,7)]"`
2. Prompt files load: `python -c "from instantdemo import prompts; [prompts.load(f'phase{n}') for n in range(1,7)]"`
3. PHASES shape: `python -c "from instantdemo.phases import PHASES; assert len(PHASES) == 6; assert PHASES[3] == 'explore'"`
4. PHASE_TOOLS coverage: assert all of phase1..phase6 are keys with non-error allowlists
5. PhaseNumber Literal: a request to `/api/project/artifacts/6` should not 422
6. Artifact-path mapping: `phase_artifact(4)` → `phase4.md`, `phase_artifact(5)` → `demo-script.json`, `phase_artifact(6)` → `phase6.md`
7. Existing smokes pass:
   - `python scripts/smoke.py` (Phase 2 only; should be unchanged behavior, ~$0.04)
   - `python scripts/smoke_segment_edit.py` (fixture-based, $0)
8. `npm --prefix frontend run build` succeeds (catches TS / phase-name reference errors)

### Live verification (small agent spend)

After plumbing passes:

9. Restore the `/tmp/shakedown` baseline fixture (already gitignored under
   `fixtures/shakedown-active-sessions-2026-05-11/`)
10. Spin up server, view in browser — phase rail shows 6 pills,
    labels `Understand / Plan / Inspect / Explore / Build / Render`
11. **Cheapest functional test**: delete `/tmp/shakedown/.instantdemo/phase4.md`
    (if it exists) and trigger Phase 4 alone via the play button on Explore.
    Expect ~$0.30–$0.80 (one Playwright probe pass against the live app).
    Verify the resulting phase4.md cites real DOM observations and
    includes the EXPLORE_OK/PARTIAL summary line.
12. **Full pipeline regression**: fresh `/tmp/shakedown` + full Regenerate.
    Compare total cost vs the previous baseline (~$2.21 pre-Explore).
    Expected to climb modestly — extra phase, but each prompt is tighter.
    Validate Render produces a video.
13. **Regression check that #47 fallbacks still work**: confirm Phase 5
    output (demo-script.json) still emits string-or-array selectors when
    Phase 4 swaps in a fallback.

### Doc / CHANGELOG (low priority)

- Note in commit message that state.json schema's semantic mapping for
  phase numbers shifted; existing projects need a re-run.
- Skill `SKILL.md` and `references/REFERENCE.md` mention phases by number
  and name; light updates wherever they refer to "Phase 4 = Build" or
  "Phase 5 = Validate/Render". Can land in a follow-up docs pass.
