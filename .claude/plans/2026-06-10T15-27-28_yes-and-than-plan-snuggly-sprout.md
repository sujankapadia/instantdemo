# M1: Explore-first Phase 1 + pre-flight + intent proposal + screenshot streaming

## Context

Second milestone of PRODUCT_PLAN.md, productionizing the §5-proven
source-free exploration (the `scripts/explore/source_free_phase1.py`
prototype). Phase 1 stops requiring a repo: it explores the LIVE APP
with Playwright (source dir becomes optional enrichment), proposes
the demo intent back to the user instead of demanding a filled form,
streams screenshots into the GUI while exploring, and the New
Project form gains pre-flight (URL probe + screenshot) and an
optional product one-pager. Branch: `feature/explore-first-phase1`.

Settled (user-confirmed): explore-first ALWAYS with optional source
enrichment (one prompt); two-run confirmation flow (cold start =
phases [1] → confirm card → phases [2..6]; Regenerate stays [1..6]);
docs/one-pager input ships in M1; jail default-ON in the server
(CLI keeps env opt-in); CLI behavior otherwise frozen.

## The two-run flow

1. New Project form: URL (+optional source, +optional docs textarea,
   +brief). Debounced `POST /api/preflight` on URL entry → thumbnail
   + title, soft gate (warn, never block).
2. Cold start POSTs `phases: [1]`. Phase 1 explores via
   Bash+Playwright, saves PNGs to `.instantdemo/exploration/`
   (streamed via new `screenshot` SSE events → RightPane filmstrip),
   ends with a fenced-JSON payload (app_model + proposed_intent +
   screens + warnings) via the existing `run_structured_query`.
   Runner records proposal to state.json; phase1.md = rendered view
   (ANSWER block preserved → narrate.py fallback chain + CLI compat).
3. IntentConfirmCard (IntentEditor prefilled: user values win,
   proposal fills blanks) → Confirm → `POST /api/runs`
   `{phases:[2..6], intent}` (existing intent.json save path);
   `intent_confirmed: true` marker in state.json. Card visibility is
   derived from `/api/project` (proposal present + not confirmed) so
   reloads re-show it.

## Phase 1 payload contract

```json
{
  "app_model": "<markdown: what the app does, screens, access, demo-relevant observations>",
  "proposed_intent": {"goal": "...", "audience": null, "tone": null,
                      "length": null, "focus": [], "excludes": [], "addenda": []},
  "screens": [{"name": "...", "route": "/x", "screenshot": "002-x.png", "notes": "..."}],
  "warnings": ["docs said X; live app shows Y — trusted the live app"]
}
```
`proposed_intent` mirrors the Intent dataclass exactly (drops into
IntentEditor + IntentBody round-trip unchanged). Validator: app_model
non-empty; goal non-empty; audience/tone/length string-or-null;
focus/excludes/addenda lists (missing = empty); screens[].screenshot
matches `^[A-Za-z0-9._-]+\.png$`. state.json: `record_phase_metrics(1,
intent_proposal=..., screens=..., warnings=...)` (explore_findings
precedent).

## Files & changes

**`prompts/phase1.md`** (rewrite, based on the prototype's proven
prompt): explore steps; screenshot instruction with worked Playwright
snippet (PNG per visited screen, sequential kebab names, save as soon
as rendered); read-only safety rules + networkidle warning verbatim;
output contract + compact worked example; proposed-intent guidance
("refine the user's goal with observations, don't replace it").
Tokens `{url}`/`{exploration_dir}` substituted via **str.replace, NOT
str.format** (template contains JSON braces). Conditional prefix
sections built by the runner: docs (prototype's trust-rule section,
10k cap), source enrichment ("source at X; MAY Read/Glob/Grep for
hidden routes/terminology; live app is primary — verify before
reporting").

**`phases/analyze.py`** (rewrite): `exploration_dir()`; `_load_docs()`
(project/product-context.md, capped); `_build_prompt()`;
`_validate_payload()` (pure); `_render_view()` (ANSWER block first:
flow = intent.goal or describe or proposal.goal; then app_model,
screens list w/ screenshot refs, proposed intent, warnings);
`new_screenshots(dir, seen)` (pure diff helper);
`_watch_screenshots()` (asyncio task, ~1s poll, emits
`{"type":"screenshot","phase":1,"file":...,"url":"/api/project/exploration/<f>"}`).
run(): clear stale exploration PNGs; start watcher only when
event_emitter set (CLI unaffected); try/finally cancel watcher + one
final scan; `run_structured_query`; record proposal + metrics
(record_phase_result once, after final turn).

**`agent_client.py`**: `PHASE_TOOLS["phase1"] = {Bash, Read, Glob,
Grep}` (one line; Bash safety stays prompt-level per §5; file tools
jailed).

**`server/routes/runs.py`**: RunRequest += `docs: str | None`; write
`project/product-context.md` when non-empty (absent = leave existing).
Jail threading: `_ensure_client(cwd, allowed_roots)` with cache key
`(cwd, sorted roots)` — replacing `_client_cwd` (otherwise Regenerate
with a new source keeps the old jail); roots = [source?, project,
tempdir, /tmp]; `make_agent_client(cwd, allowed_roots)` exists from
#56. `intent_confirmed` marker: phases==[1] → False; intent provided
+ any phase ≥2 → True.

**New `server/routes/preflight.py`**: `POST /api/preflight {url}` →
`{ok, title, final_url, screenshot, error}`; sync Playwright probe in
`asyncio.to_thread` + `wait_for(10s)` (render.py executor lesson);
domcontentloaded, 8s goto timeout; screenshot →
state_dir/preflight.png; reject non-http(s); errors = ok:false +
plain-language message, HTTP 200 (soft gate). `GET
/api/preflight/screenshot` FileResponse (the /api/project/video
pattern). Register in app.py.

**`server/routes/project.py`**: PhaseState += intent_proposal /
screens / warnings (explicit fields, extra=allow already);
ProjectState += `intent_confirmed: bool`. New: `GET
/api/project/exploration` (sorted file list) + `GET
/api/project/exploration/{filename}` (FileResponse; filename regex
`[A-Za-z0-9._-]+\.png` + resolved-path is_relative_to check).

**Frontend** (build via `npm --prefix frontend run build`; dev via
vite):
- `api/runs.ts`: RunRequest += docs; RunEvent += screenshot variant.
- `api/project.ts`: PhaseState/ProjectState fields, ScreenInfo,
  `fetchExplorationShots()`, `runPreflight()`.
- `hooks/useRun.ts`: `screenshots` state, reset on start, append on
  screenshot events; expose.
- `NewProjectForm.tsx`: docs textarea ("Product context (optional) —
  paste a one-pager/README excerpt; the live app remains the source
  of truth"); debounced (600ms, AbortController, http(s)-only)
  pre-flight with thumbnail/title on ok, amber soft warning on fail.
- `Layout.tsx`: cold start → stash form values (`pendingSetup`),
  startRun phases [1] (intent included so the brief reaches Phase 1);
  Regenerate unchanged [1..6]. Render IntentConfirmCard when
  phases.1 completed + intent_proposal present + !intent_confirmed
  (all from /api/project → reload-safe). Pass screenshots to
  RightPane.
- New `IntentConfirmCard.tsx`: proposal + user-intent merge
  (user wins per field), screens chips, warnings, embedded
  IntentEditor (expanded), Confirm → startRun([2..6], intent)
  (pendingSetup, falling back to data.url/source after reload).
- New `Filmstrip.tsx` + RightPane: horizontal thumbnail strip
  (live SSE merged with fetchExplorationShots on mount, dedupe);
  shown when no video exists yet / during phase 1; video layout
  untouched once demo.mp4 exists.

## Tests & smoke

- `tests/test-specs/test_phase1_explore.md` FIRST (spec-first hook),
  then `tests/test_phase1_explore.py`: _validate_payload cases,
  _render_view (ANSWER block parses via checkpoints.parse_answer_block),
  new_screenshots diffing (empty/new/non-png/sorted/seen-mutation),
  preflight scheme/filename guards.
- New `scripts/smoke_phase1_explore.py` (smoke.py structure):
  self-contained fixture app (stdlib http.server serving 3 static
  HTML pages with nav links — no external app dependency);
  preflight asserts; run [1] with docs + goal; assert ≥1 screenshot
  SSE event, intent_proposal recorded, intent_confirmed false,
  exploration dir non-empty + listed by endpoint, phase1.md ANSWER
  block parses; optional --confirm: run [2] flips intent_confirmed.
  Cost ~$0.15-0.25.

## Sequencing (gate after each)

1. Branch; PHASE_TOOLS + runs.py jail threading (cache-key change) →
   pytest + `scripts/smoke.py` (no regression).
2. prompts/phase1.md + analyze.py rewrite (watcher stubbed) + docs
   field + intent_confirmed marker → unit tests; CLI run `instantdemo
   phase 1` vs live Evernote fixture app to eyeball quality.
3. Screenshot watcher + SSE event + exploration endpoints +
   PhaseState/ProjectState fields → unit test diff helper; GUI run
   [1], curl exploration endpoints.
4. preflight.py + registration → curl good/bad URLs.
5. Frontend api types + useRun + Filmstrip/RightPane → npm build,
   vite dev check.
6. NewProjectForm (docs+preflight) + Layout two-stage +
   IntentConfirmCard → manual end-to-end in dev; reload mid-flow
   re-shows card.
7. smoke_phase1_explore.py + spec + a saved fixture run → smoke
   < $0.3.
8. npm build for the served bundle; CLAUDE.md/PRODUCT_PLAN docs;
   both smokes green; user sign-off (L5); PR.

## Verification summary

- Unit: validator/view/diff-helper/guards (free, every step).
- Live gates: CLI phase-1 vs Evernote app (step 2); GUI run with SSE
  screenshot events (step 3); new smoke end-to-end (step 7);
  `scripts/smoke.py` + `smoke_phase4_rehearsal.py --scenario 5a`
  before PR (regression: phase-2 path + rehearsal unaffected).
- User acceptance: cold-start a fresh project in the GUI against the
  Evernote app — watch filmstrip populate, see pre-flight thumbnail,
  confirm proposed intent, watch [2..6] produce the demo.

## Risks

- Agent skips screenshots → worked example in prompt; empty filmstrip
  tolerated; smoke asserts ≥1.
- Payload quality → corrective retry; minimal required fields.
- Reload mid two-run flow → card derived from /api/project;
  pendingSetup falls back to data.url/source.
- Preflight blocking loop → to_thread + wait_for (sync Playwright off
  the loop thread).
- source=None + jail → roots always include project + tempdirs.
- Stale PNGs on re-run → cleared at phase start.
