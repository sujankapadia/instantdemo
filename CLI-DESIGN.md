# InstantDemo CLI — Design

Plan for converting the existing Claude Code skill (`plugins/instantdemo/skills/generate-demo/SKILL.md`) into a standalone, `pip`-installable CLI built on the [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python).

## Why

Today InstantDemo is only usable inside a Claude Code session. A standalone CLI:
- Distributes via `pip install instantdemo` (no Claude Code dependency at runtime)
- Embeds in CI/CD (auto-regenerate demo videos on deploy)
- Is callable from scripts, agents, and any environment with Python + a Claude subscription

The CLI replaces the skill's role as the primary entrypoint. The skill stays — repurposed as a thin Claude Code-native UX wrapper that depends on the same engine (see "Renderer & Skill Coupling" below).

## What's Already Decided

These are settled — they're inputs to the implementation, not open questions.

### Spike outcome
The Agent SDK can reproduce Phase 1 (codebase analysis) at parity with the skill on `claude-code-analytics`: $0.18, 44s, 19 turns, no material misses. Spike repo: `https://github.com/sujankapadia/instantdemo-sdk-spike` (private). REPORT.md and spike.py there are the working reference for the `query()` invocation pattern.

### Audience
Developers. The CLI is the MVP target; a GUI version comes later (see Obsidian: "InstantDemo - GUI App Vision"). No manual / drag-drop mode in V1.

### Auth
OAuth via the locally-authenticated `claude` CLI session. The SDK handles this transparently — no API key, no setup step. Confirmed in spike.

### State management
**File handoff** between phases. Each phase is a fresh `query()` call that takes the prior phase's artifact (a markdown or JSON file) as context. Not a single multi-turn session.

Why: resumability (`--from-phase N`), debuggability, $EDITOR checkpoint UX, smaller per-phase prompts. Tradeoff (no implicit context-sharing) is paid by stuffing prior-phase output into the next phase's prompt — a few KB of markdown.

### Phase artifact format
- **Phases 1–3**: markdown — agent prose, meant for human review
- **Phase 4 (script)**: JSON — structured, consumed by the renderer
- **Metrics**: JSON Lines — one object per `generate` run

### Checkpoints
$EDITOR opens automatically after each phase that produces an artifact. Falls back to print-and-wait when stdin/stdout isn't a TTY (CI use). `--no-edit` flag opts out manually. Future `--auto` flag (Issue #1) skips checkpoints entirely.

For phases that need *answers* (not just review), a structured block at the top of the markdown lets the user fill in:

```markdown
<!-- ANSWER THESE BEFORE CONTINUING -->
flow: <which flow to demo>
url: http://localhost:3000
seed_data_ready: yes|no
<!-- /ANSWER -->

# Codebase Analysis
[agent output]
```

The next phase's runner parses these out before building the prompt.

### Per-phase tool scoping
Each phase gets the minimum tools it needs. Tighter than the skill's global allowlist:

| Phase | Tools | Notes |
|---|---|---|
| 1 — Analyze | `Read`, `Glob`, `Grep` | Read-only exploration. Spike-validated. |
| 2 — Narrate | _(none)_ | Pure reasoning over Phase 1 output |
| 3 — Gather | `Read`, `Glob`, `Grep` | Re-explore frontend for selectors |
| 4 — Script | `Write` | Output `demo-script.json` |
| 5 — Validate | `Bash(curl *)`, `Bash(python *)`, `Read` | URL check + Playwright selector probe |

`permission_mode="bypassPermissions"` everywhere (spike confirmed it works cleanly with read-only sets).

### Prompt reuse
Use skill prompts verbatim where possible. The spike confirmed they work as-is in the SDK. Strip:
- `**Checkpoint — STOP and wait for user input**` directives → CLI handles flow
- `AskUserQuestion` references → answer block in markdown
- `${CLAUDE_SKILL_DIR}/references/REFERENCE.md` reference → embed schema directly
- The Phase 5 `${CLAUDE_SKILL_DIR}/scripts/render.py` invocation → CLI runs render directly

### Repo location: existing `instantdemo` repo
Everything lives here. New `src/instantdemo/` Python package alongside the existing `plugins/instantdemo/` skill bundle. Single source of truth, single backlog. See "Repo Layout" below.

### Renderer & skill coupling: C1 (plugin depends on pip package)
The renderer moves from `plugins/instantdemo/skills/generate-demo/scripts/render.py` to `src/instantdemo/render.py`. The skill no longer ships a renderer; it invokes `instantdemo render ...` instead. Skill prerequisites add `pip install instantdemo[kokoro]`.

This means **existing skill users will need to `pip install instantdemo` after this lands** — a one-time migration, document in changelog.

## Repo Layout

```
instantdemo/
├── .claude-plugin/marketplace.json              # unchanged
├── plugins/instantdemo/
│   ├── .claude-plugin/plugin.json               # unchanged
│   └── skills/generate-demo/
│       ├── SKILL.md                             # UPDATED: Phase 5 calls `instantdemo render ...`
│       ├── references/REFERENCE.md              # unchanged (still the source for the schema)
│       ├── assets/example-script.json           # unchanged
│       └── scripts/                             # REMOVED — render.py moves out
├── src/instantdemo/                             # NEW — the pip package
│   ├── __init__.py
│   ├── cli.py                                   # argparse, subcommand dispatch
│   ├── phases/
│   │   ├── __init__.py
│   │   ├── analyze.py                           # Phase 1
│   │   ├── narrate.py                           # Phase 2
│   │   ├── gather.py                            # Phase 3
│   │   ├── script.py                            # Phase 4
│   │   └── validate.py                          # Phase 5
│   ├── prompts/
│   │   ├── phase1.md                            # extracted from SKILL.md
│   │   ├── phase2.md
│   │   ├── phase3.md
│   │   ├── phase4.md
│   │   └── phase5.md
│   ├── checkpoints.py                           # $EDITOR flow + answer-block parsing
│   ├── state.py                                 # .instantdemo/ read/write
│   ├── metrics.py                               # ResultMessage capture → metrics.jsonl
│   └── render.py                                # MOVED from plugin
├── tests/                                       # NEW
├── pyproject.toml                               # NEW
├── README.md                                    # UPDATED — documents both skill and CLI
├── CLAUDE.md
├── TTS-PROVIDERS.md
└── LICENSE
```

`src/` layout is the modern Python convention — keeps the package importable only after install (catches "I forgot to install" bugs early).

## CLI Surface

```bash
# Default: end-to-end with editor checkpoints
instantdemo generate \
  --url http://localhost:3000 \
  --source ./src \                          # default: cwd
  --describe "show the signup flow" \       # optional, like skill's $ARGUMENTS
  --tts kokoro \                            # default
  --output demo.mp4

# Resume after editing intermediate output
instantdemo generate --from-phase 3

# Render-only (script already exists)
instantdemo render demo-script.json --tts kokoro -o demo.mp4

# Single phase (debugging / dev iteration)
instantdemo phase 1
instantdemo phase 2

# No-editor variants
instantdemo generate --no-edit            # runs through, never opens $EDITOR
                                           # (still pauses for review at checkpoints unless --auto)
```

`generate` is the verb everyone uses. `phase` and `render` are escape hatches. The future `--auto` flag (Issue #1) attaches to `generate`.

## .instantdemo/ Directory Contract

Lives in the user's project root, alongside `.git/`. User can gitignore or commit per preference.

```
.instantdemo/
├── phase1.md                # Codebase analysis + answer block
├── phase2.md                # Narrative plan (segments, draft narration, proposed actions)
├── phase3.md                # Technical details (selectors, waits, pacing)
├── state.json               # Which phases ran, timestamps, per-phase summary
└── metrics.jsonl            # One ResultMessage capture per phase per run
demo-script.json             # Phase 4 output, lives in project root (user-facing)
demo.mp4                     # Phase 5 final output
```

`state.json` schema (rough):
```json
{
  "session_id": "uuid",
  "url": "http://localhost:3000",
  "describe": "show the signup flow",
  "phases": {
    "1": {"status": "completed", "started_at": "...", "completed_at": "...", "cost_usd": 0.18},
    "2": {"status": "completed", ...},
    "3": {"status": "pending"}
  }
}
```

## pyproject.toml Sketch

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "instantdemo"
version = "0.1.0"
description = "Generate narrated demo videos of web applications"
requires-python = ">=3.11"
dependencies = [
    "claude-agent-sdk>=0.1.71",
    "playwright>=1.40",
]

[project.optional-dependencies]
kokoro = ["kokoro>=0.9.4", "soundfile"]
piper = ["piper-tts", "pathvalidate"]
all-tts = ["kokoro>=0.9.4", "soundfile", "piper-tts", "pathvalidate"]
dev = ["pytest", "ruff"]

[project.scripts]
instantdemo = "instantdemo.cli:main"

[tool.hatch.build.targets.wheel]
packages = ["src/instantdemo"]
```

System prerequisites (not installable via pip): `ffmpeg`, `playwright install chromium`. README documents these.

## Metrics

Per the GUI Vision note, log token usage from day one to inform future hosted-pricing decisions.

After each phase's `query()` call, append a row to `.instantdemo/metrics.jsonl`:

```json
{"timestamp": "2026-04-08T...", "phase": "analyze", "session_id": "...", "cost_usd": 0.18, "duration_ms": 44500, "duration_api_ms": 43600, "num_turns": 19, "input_tokens": 1796, "output_tokens": 2739, "cache_creation_tokens": 26373, "cache_read_tokens": 123273, "is_error": false}
```

One line per phase per run. Easy to analyze later (jq, pandas, whatever).

## Implementation Order

The skeleton-first sequence below front-loads packaging and infrastructure so each phase port runs end-to-end as it lands.

1. **Package skeleton** — `pyproject.toml`, `src/instantdemo/__init__.py`, `src/instantdemo/cli.py` with `instantdemo --version` + `instantdemo --help` working. `pip install -e .` succeeds.
2. **Move renderer** — `plugins/instantdemo/skills/generate-demo/scripts/render.py` → `src/instantdemo/render.py`. Add `instantdemo render` subcommand wrapping it. Update SKILL.md Phase 5 path. Smoke-test that the skill still works end-to-end.
3. **CLI scaffold** — `generate`, `phase`, `render` subcommands wired with argparse. No AI calls yet. Stub each phase to write a placeholder file under `.instantdemo/`.
4. **Checkpoints + state** — `checkpoints.py` ($EDITOR flow, TTY detection, `--no-edit` flag, answer-block parser). `state.py` (read/write `.instantdemo/state.json`). Test against the stub phases.
5. **Phase 1 port** — extract Phase 1 prompt to `src/instantdemo/prompts/phase1.md`, build the runner using the spike's `query()` pattern. End-to-end run produces real `phase1.md`.
6. **Phase 2 port** — Phase 2 prompt → `src/instantdemo/prompts/phase2.md`. Runner takes Phase 1 output as context. No tools.
7. **Phase 3 port** — Phase 3 prompt + Phase 2 narrative as input. Read-only tools.
8. **Phase 4 port** — Phase 4 prompt embeds the schema (no `${CLAUDE_SKILL_DIR}/references/REFERENCE.md` reference). Writes `demo-script.json`.
9. **Phase 5 port** — Validation phase (curl + Playwright probe), then invokes the renderer.
10. **Metrics** — `metrics.py`. Capture from each `ResultMessage` and append to `.instantdemo/metrics.jsonl`.
11. **End-to-end test** — `instantdemo generate --url http://localhost:5173 --source /path/to/claude-code-analytics`. Should produce a real MP4.
12. **Packaging polish** — README updates, `pip install instantdemo[kokoro]` works in a fresh venv, CHANGELOG entry for the skill migration.

## Out of Scope (deferred)

- `--auto` flag → [Issue #1](https://github.com/sujankapadia/instantdemo/issues/1)
- Manual mode (drag-drop operation builder) → GUI scope
- Smart re-render (reuse browser footage when only narration changed) → GUI scope
- Hosted SaaS version → see "InstantDemo - GUI App Vision" Obsidian note
- Web/GUI frontend → next phase after CLI ships

## References

- **Spike report**: `/Users/user/dev/personal/instantdemo-sdk-spike/REPORT.md`
- **Spike code (use as `query()` template)**: `/Users/user/dev/personal/instantdemo-sdk-spike/spike.py`
- **Source skill**: `plugins/instantdemo/skills/generate-demo/SKILL.md`
- **Schema reference (for Phase 4)**: `plugins/instantdemo/skills/generate-demo/references/REFERENCE.md`
- **--auto flag tracking issue**: https://github.com/sujankapadia/instantdemo/issues/1
- **Vision docs (Obsidian)**: `Claude Code/Agentic Workflows/Instant Demo/`
  - `InstantDemo - From Skill to Standalone App.md`
  - `InstantDemo - GUI App Vision.md`
- **Agent SDK docs**: https://docs.claude.com/en/api/agent-sdk/python
