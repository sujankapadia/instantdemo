# GUI Design Decisions

All v1 decisions resolved. This doc captures the choices made during
design discussion so future implementation work has a single source
of truth.

Status legend: **Resolved** = decided. **Deferred** = punted to v1.5+.

---

## A. Cold-start flow

### A1. Auto-advance through phases by default
**Status:** Resolved
**Decision:** Yes, auto-advance is the default. A "Pause between
phases" toggle in the header lets power users opt into CLI-style
checkpoints.
**Rationale:** Artifacts are always editable retroactively in the
GUI, so blocking on review is unnecessary by default.

---

## B. Per-segment editing & re-rendering

**Scope decision:** The per-segment inline editor in v1 edits
**narration text and `pause_after_ms` only**. All structural fields
(action, selector, url, value, frame, wait_for, key) are NOT edited
inline. The premise of the product is that AI generates the script;
humans iterate on the spoken text and pacing. Anything structural is
fixed by re-running an upstream phase or by direct JSON editing in
the Phase 4 artifact view (the power-user escape hatch).

This rules out building a selector picker, recorder UI, or any
codegen-equivalent functionality. We are explicitly not redeveloping
Playwright codegen with a nicer UI.

### B1. Re-render granularity
**Status:** Resolved
**Decision:** Two buttons per segment.
- **"Re-render audio"** — for narration text changes. Cheap (~5–10s).
  Re-runs TTS for that segment's narration, swaps the audio track,
  re-muxes. No re-recording.
- **"Re-render segment"** — for `pause_after_ms` changes. Medium cost
  (~15–30s) if lengthening pause; cheap if shortening (re-trim only).

### B2. Reordering segments (drag to swap)
**Status:** Deferred to v1.5+
**Reason:** Reordering AI-generated segments breaks the narrative
flow the agent designed. The right answer is "re-run Phase 2 with a
different prompt," not manual reorder.

### B3. Inserting new segments
**Status:** Deferred to v1.5+
**Reason:** Inserting requires picking an action and selector for
the new segment, which the v1 scope decision excludes.

### B4. Deleting segments
**Status:** Deferred to v1.5+
**Reason:** Cascades to downstream state. If a segment is bad, the
right answer is re-running Phase 4 with a hint.

### B5. Visual segment dependency highlighting
**Status:** Not needed
**Reason:** Irrelevant once structural edits are out of scope. Cost
previews on the two re-render buttons (B1) are sufficient.

### B6. `pause_after_ms` editable in v1
**Status:** Resolved
**Decision:** Yes, editable. Accept re-record-on-lengthen as the v1
cost; if the continuous-recording trim plan
(`.claude/plans/2026-03-23T12-44-04_dreamy-stargazing-flask.md`)
lands later, lengthening becomes cheap automatically.
**Rationale:** Pacing tuning is a primary iteration use case and
shouldn't require an upstream re-run.

---

## C. Phase-level workflow

### C1. Stale-state cascade behavior
**Status:** Resolved
**Decision:** Flag-and-wait. When a user edits something upstream,
downstream phase pills get a yellow "stale" indicator. User clicks
"Re-run from here" (cascade all downstream) or "Re-run only this
phase" when ready.
**Rationale:** Cascading downstream costs $0.50–1 in Claude usage per
run. Users iterate on prompts, batch multiple edits, and experiment
with prompt variations — auto-cascade would burn money on every save.
Manual control is worth the small UX cost of the stale indicator.

### C2. Where the prompt editor lives
**Status:** Resolved
**Decision:** Per-project style file only (`instantdemo-style.md`,
issue #4). No per-phase prompt template editor in v1.
**Rationale:** The style file covers the actual user need — adding
guidance like "avoid marketing language, our brand voice is direct" —
without exposing bundled prompt internals. Users add to the file; the
file is layered into every prompt run as additional guidance. One
concept, one file. Power users who need to fundamentally rewrite
agent behavior can fork the package; v1.5+ can revisit a per-phase
editor if real demand emerges.

---

## D. Agent log / streaming output

### D1. Persistence of agent log across sessions
**Status:** Resolved
**Decision:** Persist per-run. Each phase run's full agent transcript
saved to `.instantdemo/runs/<timestamp>/<phase>.log`. A "Run history"
view (v1.5) can browse past runs.
**Rationale:** Cheap (text logs, kilobytes), useful for debugging
"why did Phase 3 produce a weird selector last Tuesday."

---

## E. Project & header chrome

### E1. Single project vs multi-project dashboard
**Status:** Resolved
**Decision:** Single-project. GUI opens on whatever directory you
ran `instantdemo serve` in. Like running `code .` — directory-scoped.
Multi-project dashboard is v2 if demand emerges.

### E2. How the user invokes the GUI
**Status:** Resolved
**Decision:** `instantdemo serve` from the project directory.
Browser opens to localhost.
**Rationale:** Same install story as the CLI, zero new packaging
surface, project context implicit from cwd.

### E3. GUI managing the target web app
**Status:** Resolved
**Decision:** Inherit. GUI assumes the user has already started
their target app (e.g., `npm run dev` in another terminal).
**Rationale:** Managing the dev server is a deep rabbit hole
(process lifecycle, port detection, logs, env vars, multi-service
apps). Defer to v2+ if real demand emerges.

### E4. Privacy indicator in the header
**Status:** Resolved
**Decision:** Hide. No indicator.
**Rationale:** Marketing-flavored UI element with low value. If
privacy positioning becomes important later, it can live in landing
page copy or docs rather than app chrome.

---

## F. Script-level settings

### F1. Where script-level fields live
**Status:** Resolved
**Decision:** Project settings panel, accessed via a gear icon in
the header. Hosts: title, resolution, TTS provider/voice, auth_state
path (issue #7).
**Note:** The Phase 4 artifact view is also the power-user JSON
editor for the entire script. Anything not exposed in dedicated UI
(selectors, actions, structural fields, segment order) can be edited
there directly. This is the v1 escape hatch.

### F2. Per-segment voice override
**Status:** Deferred
**Reason:** Adds complexity to the schema and the editor. Most demos
use one voice. Revisit if users ask.

---

## G. Engine integration

### G1. How the GUI invokes the engine
**Status:** Resolved
**Decision:** Import the `instantdemo` package directly, call phase
functions in-process. Stream agent output via internal callbacks.
The CLI and GUI server become peer clients of the same engine.
**Rationale:** Streams cleanly to the browser via SSE, holds project
state in memory, supports cancellation via SDK interfaces. Subprocess
shell-out would add latency and complicate streaming.

### G2. Streaming protocol
**Status:** Resolved
**Decision:** Server-Sent Events (SSE).
**Rationale:** Data flow is one-way (server → client). SSE is
simpler in FastAPI, simpler in the browser, no WebSocket
infrastructure needed. Switch to WebSocket only if bidirectional
control becomes necessary (e.g., chat-like interaction with the
agent).

### G3. Long-lived `ClaudeSDKClient` instead of `query()` per phase
**Status:** Resolved — shipped as Iteration 12 (commit 40d9493).

**Context:** SDK spike confirmed that `claude-agent-sdk` launches
the `claude` CLI as a subprocess on every `query()` call, paying
~5–10s cold-start per phase. A 5-phase cold-start workflow burns
~25–50s before any real work. `ClaudeSDKClient` reuses one
subprocess across queries, paying the cold-start once.

**Implementation actually shipped:**

| Metric | `query()` × 5 phases (before) | `ClaudeSDKClient` reused (after) |
|---|---|---|
| Cold-start cost | ~30s total | ~5s once |
| Subsequent query latency | 5–10s subprocess startup | ~2s |
| Cancellation | `asyncio.cancel` ~6s | `client.interrupt()` ~instant |
| Per-phase context isolation | Implicit (fresh subprocess) | Via `session_id` argument to `client.query()` |
| Per-phase tool allowlist | `ClaudeAgentOptions(allowed_tools=...)` per call | `PreToolUse` hook + `PhaseDispatcher` |

Migration touched all 5 phase modules and the CLI. Phase `run()`
became `async`; CLI's `cmd_generate` / `cmd_phase` wrap a single
`asyncio.run` that owns the client lifecycle (connect → run phases
→ disconnect in finally). Engine-level migration so both CLI and
GUI benefit.

**Tool dispatcher: `can_use_tool` doesn't work; `PreToolUse` hook
does.**

The original plan was to use the SDK's `can_use_tool` callback to
preserve per-phase allowlists on a shared client. Implementation
revealed the callback only fires when the CLI is *about to prompt
the user* — which it skips entirely under `bypassPermissions`, and
also skips when `--allowedTools` isn't passed (the SDK omits the
flag when `allowed_tools=[]`, so the CLI defaults to allowing all
tools, and never asks for permission). Empirically the callback
never fired in any of four permission modes tested.

The mechanism that works is a `PreToolUse` hook, which fires
unconditionally before every tool call and returns an
allow/deny decision. The hook needs to know which phase is
currently active. Two approaches that *don't* work:
- The SDK's `session_id` field in the hook input is an SDK-internal
  UUID, not the user-supplied `session_id=` argument to
  `client.query()`. So we can't read the phase name from there.
- `ContextVars` set in the orchestrator don't propagate across the
  SDK's internal task boundary, so the hook callback can't read
  them.

The mechanism that *does* work is a small `PhaseDispatcher` class
holding `current_phase` as an instance attribute. The orchestrator
sets it before each phase's queries (via `run_query_on_client`)
and resets in a `finally`. The hook is a bound method, so it sees
each mutation directly. **Constraint: phases must run sequentially
on a given dispatcher.** Concurrent queries on the same client
would race the attribute. Acceptable for the current pipeline;
documented in the agent_client module.

**Other tradeoffs (mostly deferred):**
- Refactoring cost paid in Iteration 12 — touched 5 phase files,
  the CLI, and the Context dataclass. Mechanical.
- Single-subprocess assumption — if the GUI ever gets multi-user
  concurrent runs, we'd need either a client pool or to enforce
  serialization. Not a v1 concern.
- Subprocess crash recovery — with `query()` each phase had its own
  subprocess; with `ClaudeSDKClient` a crash blocks all subsequent
  phases until reconnect. Health check + reconnect path is a
  follow-up worth filing if it ever bites; not needed for MVP.

**Verified end-to-end** by re-running Phase 2 against the
claude-code-analytics fixture: cost $0.04, 30.8s, 1 turn —
consistent with prior `query()`-based runs. PhaseDispatcher
deny path tested in isolation against synthetic queries before
integrating.

---

## H. Frontend stack

### H1. Frontend framework
**Status:** Resolved
**Decision:** React + Vite.
**Rationale:** Most developers know React; ecosystem is rich for
editors (CodeMirror), markdown, video. Bundle is heavier than Svelte
but irrelevant for localhost.

### H2. Code/markdown editor
**Status:** Resolved
**Decision:** CodeMirror 6 for markdown (phases 1/2/3/5 artifacts,
prompt template / style file) and JSON (Phase 4 artifact). Plain
textarea for narration text per segment in the inline editor.
**Rationale:** CodeMirror 6 is lighter than Monaco with sufficient
syntax highlighting and JSON validation. Single component handles
both markdown and JSON modes.

---

## Summary

All 14 original v1 decisions resolved. Ready for implementation
planning.

**G3 (`ClaudeSDKClient` migration)** shipped as Iteration 12 of M2
(commit 40d9493). Implementation diverged from the original
`can_use_tool`-based plan — see the G3 section for the full
post-mortem.

Deferred to v1.5+: B2 reorder, B3 insert, B4 delete, F2 per-segment
voice. Per-phase prompt template editor (an option considered in C2)
also deferred.

Not built: B5 dependency visualization (not needed), E4 privacy
indicator (no value).
