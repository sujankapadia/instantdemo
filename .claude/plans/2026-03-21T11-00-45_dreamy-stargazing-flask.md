# Plan: Restructure InstantDemo as a Claude Code Skill

## Context

InstantDemo is currently a standalone Python script (`run_demo.py`) that renders narrated demo videos from JSON script definitions. We want to restructure it as a Claude Code skill that teaches the agent to analyze a codebase, generate a demo script JSON, validate it, and render it — all bundled together. The rendering script stays Python; the skill provides the prompt engineering that makes the agent a "product marketer who can read code."

The skill handles script generation (the creative/analytical part). Rendering is a separate step — the user reviews and tweaks the script, then runs the render command when satisfied.

## Target Structure

```
~/.claude/skills/generate-demo/
├── SKILL.md                        # Agent instructions (5 phases)
├── reference.md                    # JSON schema, examples, narration guide
├── scripts/
│   └── render.py                   # Restructured from run_demo.py
└── templates/
    └── example-script.json         # Active-sessions example for reference
```

## Step 1: Create `reference.md`

Source files: `/Users/user/dev/personal/instantdemo/PIPELINE.md`, `/Users/user/dev/personal/instantdemo/CLAUDE.md`, `/Users/user/dev/personal/instantdemo/active-sessions-script.json`

Contents:

- **Rendering engine** — explain that render.py uses **Playwright** for browser automation. Actions in the script map to Playwright `page` methods, selectors use Playwright's selector syntax (CSS selectors, `data-testid` attributes, text selectors, etc.).
- **JSON schema** — top-level fields (`title`, `resolution`, `segments`). Actions are **open-ended Playwright page method names** (not a fixed set). Document common actions (`goto`, `click`, `fill`, `hover`, `scroll`, `wait`) with their expected fields, but the agent can use any valid Playwright page method. Each segment always has `narration`, `action`, and `pause_after_ms`.
- **Annotated example** — the active-sessions script with comments explaining each decision
- **Common patterns** — SSE/websocket workaround (`domcontentloaded` + `wait_for_selector`), auth bypass, scroll-then-wait for lazy loading, form filling
- **Narration guide** — recommended defaults (short sentences, present tense, spoken-word style) but explicitly noted as overridable. The agent should ask the user about tone/style/audience preferences before writing narration.

## Step 2: Restructure `run_demo.py` → `scripts/render.py`

Source file: `/Users/user/dev/personal/instantdemo/run_demo.py`

### 2a. CLI arguments
- Add `script` as **positional** argument (required, the JSON script path)
- Keep `--tts` (default: google) and `-o/--output`
- Add `--env` flag (path to .env, default: `.env` in CWD)
- Add `--piper-model` flag (path to Piper ONNX model, falls back to `PIPER_MODEL_PATH` env var)
- Default output: `{script_stem}-demo.mp4` in CWD (derived from script filename when `-o` not given)

### 2b. Remove hardcoded paths
- Remove `DEMO_DIR = Path(__file__).parent` and `OUTPUT_DIR = DEMO_DIR / "output"` globals
- Create a `resolve_paths(args)` function that computes all paths from CLI args
- Temp files go to `tempfile.mkdtemp(prefix="instantdemo-")` (OS `/tmp`, cleaned up by OS on reboot). Print the tmp dir path to console so users can find files for debugging if render fails.

### 2c. Open-ended action dispatch
Replace the hardcoded `if action == "navigate" ... elif action == "click"` chain with a dynamic dispatch that maps script actions to Playwright page methods. Common actions (`goto`, `click`, `fill`, `hover`, `scroll`) get argument mapping; unknown actions fall back to `getattr(page, action)` with the segment's fields as kwargs. This lets the agent use any Playwright method without requiring render.py changes.

### 2d. Thread config through functions
- TTS functions gain `tmp_dir` + provider-specific params (`env_path` or `piper_model`)
- `record_browser_video` gains `tmp_dir` param for `record_video_dir`
- `combine_audio_video` gains `tmp_dir` param for concat list, silence clips, combined audio
- `_ensure_wav` gains `tmp_dir` param
- Replace `TTS_PROVIDERS` dict with conditional dispatch (functions no longer share a uniform signature)

### 2e. Provider-specific config validation
Only validate config for the selected provider — don't error on missing GCP_PROJECT if using ElevenLabs, etc.:
- `--tts google` → requires `GCP_PROJECT` env var + gcloud auth (remove hardcoded `august-tangent-490821-h5` fallback)
- `--tts elevenlabs` → requires `ELEVENLABS_API_KEY` + `ELEVENLABS_VOICE_ID`
- `--tts piper` → requires `--piper-model` or `PIPER_MODEL_PATH` env var

### 2f. Update docstring
Reflect new CLI usage and positional script argument.

## Step 3: Copy example script

Copy `/Users/user/dev/personal/instantdemo/active-sessions-script.json` to `templates/example-script.json`. No changes.

## Step 4: Write `SKILL.md`

Frontmatter:
```yaml
---
name: generate-demo
description: Generate a narrated demo video of a web application. Analyzes codebase, produces a demo script, validates it, and renders video. Use for product walkthroughs, demos, screencasts.
disable-model-invocation: true
allowed-tools:
  - Read
  - Glob
  - Grep
  - Write
  - Bash(python *)
  - Bash(curl *)
---
```

Body — five phases with interactive checkpoints:

**Phase 1: Understand the product**
- Read README, CLAUDE.md, docs for product context and value prop
- Read route definitions (React Router, Next.js pages, SvelteKit routes, etc.)
- Read top-level page components (not every file)
- Check for seed data / fixtures / dev setup (`seed.py`, `fixtures.json`, docker-compose)
- Check for auth (dev credentials, login bypass, `.env.example`)
- **Checkpoint**: Summarize findings and ask the user which flow to demo (present options derived from discovered routes/features)

**Phase 2: Plan the narrative**
- Ask user about tone/style/audience preferences (casual/formal, technical/non-technical). Default to: short sentences, present tense, spoken-word style if no preference given.
- Choose one compelling flow showing the core value prop
- 4-8 segments, target 30-60 seconds
- Lead with the payoff — show the impressive result early
- **Checkpoint**: Present the narrative plan to the user for approval before continuing

**Phase 3: Gather technical details**
- For each segment, find stable selectors (prefer: `data-testid` > `aria-label` > semantic HTML > avoid generated classnames)
- Identify wait conditions — what indicates the page is ready? (element appearing, data loaded)
- Flag SSE/websocket pages — use `domcontentloaded` + `wait_for_selector`, never `networkidle`
- The rendering pipeline uses **Playwright** — actions in the script map to Playwright `page` methods. Use whatever method fits (goto, click, fill, hover, etc.). Selectors must be Playwright-compatible (CSS selectors, `data-testid`, text selectors).
- Estimate pacing: 1500-2500ms after visual changes, 500-1000ms for simple waits

**Phase 4: Produce the script JSON**
- Read `${CLAUDE_SKILL_DIR}/reference.md` for schema and examples
- Write the JSON to a file (suggest `demo-script.json` in project root, or ask user)

**Phase 5: Pre-render validation**
- Check URLs reachable: `curl -s -o /dev/null -w "%{http_code}" <url>`
- Check selectors exist: write and run a quick Playwright script that navigates + `query_selector`
- Confirm app has data (pages show content, not empty states)
- **Checkpoint**: On success, show the render command and let the user decide when to run:
  ```bash
  python ${CLAUDE_SKILL_DIR}/scripts/render.py demo-script.json --tts google -o demo.mp4
  ```

## Step 5: Update project documentation

- Update `/Users/user/dev/personal/instantdemo/CLAUDE.md` — note the project is now packaged as a Claude Code skill, add installation instructions
- Update `/Users/user/dev/personal/instantdemo/README.md` — add skill installation section

## Implementation Order

1. `reference.md` and `scripts/render.py` — independent, can be parallel
2. `templates/example-script.json` — trivial copy
3. `SKILL.md` — depends on 1 and 2 for references
4. Update repo docs — depends on all above

## Verification

1. **render.py CLI**: `python ~/.claude/skills/generate-demo/scripts/render.py --help` shows new argument structure with positional script arg
2. **render.py renders**: `python ~/.claude/skills/generate-demo/scripts/render.py active-sessions-script.json --tts google -o test.mp4` (requires claude-code-analytics running on localhost)
3. **Skill loads**: `/generate-demo` in any project shows the skill instructions
4. **End-to-end**: invoke `/generate-demo` in a project with a running web app, verify it produces a valid script JSON and the render command works
