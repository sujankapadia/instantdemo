---
name: generate-demo
description: Generate a narrated demo video of a web application. Analyzes codebase, produces a demo script, validates it, and renders video. Use for product walkthroughs, demos, screencasts.
disable-model-invocation: true
argument-hint: [description of what to demo]
allowed-tools:
  - Read
  - Glob
  - Grep
  - Write
  - Bash(python *)
  - Bash(curl *)
---

# Generate Demo Video

You are generating a narrated demo video of a web application. Your job is to analyze the codebase, understand the product, and produce a JSON script that drives the rendering pipeline. Work through the phases below, pausing for user input at each checkpoint.

If the user provided a description of what to demo (`$ARGUMENTS`), use that as the target flow. You should still do Phase 1 analysis to understand the codebase, but skip the "which flow?" question at the checkpoint — the user already told you.

## Prerequisites

The rendering pipeline requires the `instantdemo` Python package, plus Chromium and ffmpeg. Install with:

```bash
pip install 'instantdemo[kokoro]'   # bundles the renderer + Kokoro TTS
playwright install chromium
brew install ffmpeg                 # or your platform's package manager
```

Other TTS providers can be selected at render time: `--tts google` (requires `gcloud auth login`), `--tts elevenlabs` (requires API key), `--tts piper` (requires a local model file).

If `instantdemo` isn't installed, tell the user what's needed before proceeding.

## Phase 1: Understand the Product

Analyze the codebase to understand what this application does and how it works.

1. **Read product context**: README, CLAUDE.md, docs/, any marketing or onboarding copy
2. **Read route definitions**: Find the router config (React Router, Next.js pages/, SvelteKit routes/, Vue Router, etc.) to understand all available screens
3. **Read top-level page components**: For each route, read the main page component to understand what it renders. Don't read every file — just the page-level components.
4. **Check for seed data / fixtures**: Look for `seed.py`, `fixtures.json`, `docker-compose.yml`, database migrations, or setup scripts that populate the app with sample data
5. **Check for auth**: Is there a login? Look for dev credentials in `.env.example`, README, or a local auth bypass. Note what's needed to access the app.

**Checkpoint — STOP and wait for user input**: Summarize what the app does, list the main screens/features, and use the `AskUserQuestion` tool to ask:
- Which flow or feature should the demo showcase?
- Is the app currently running? On what port?
- Is there seed data loaded, or do we need to set that up first?

Do NOT proceed to Phase 2 until the user responds.

## Phase 2: Plan the Narrative

Design the demo's story arc before writing any JSON.

First, ask the user about preferences (or use defaults if they don't have a preference):
- **Tone**: casual (developer advocate) vs. formal (enterprise sales). Default: casual.
- **Audience**: technical (developers) vs. non-technical (end users, execs). Default: technical.
- **Terminology**: any specific product names or feature names to use?

Then plan the narrative:
- **Pick one compelling flow** that shows the core value proposition
- **4-8 segments**, targeting 30-60 seconds total
- **Lead with the payoff** — show the impressive result early, then explain how you got there
- **Narration defaults** (override per user preference): short sentences (<15 words), present tense, spoken-word style, no jargon, contractions OK
- Use empty narration (`""`) for setup segments like login or scrolling to position

**Checkpoint — STOP and wait for user input**: Present the narrative plan as a numbered list of segments with draft narration and proposed actions. Use the `AskUserQuestion` tool to ask for approval. Do NOT proceed to Phase 3 until the user approves.

## Phase 3: Gather Technical Details

For each segment in the approved narrative, find the implementation details.

**Selectors** (in order of preference):
1. `data-testid` attributes — most stable
2. `aria-label` or `role` attributes — semantic and stable
3. Semantic HTML (`button[type='submit']`, `a[href*='/dashboard']`) — usually stable
4. Avoid: generated class names (`.css-1a2b3c`, `.MuiButton-root`)

**Wait conditions**:
- What indicates the page is ready? An element appearing? An API response rendering?
- For pages with SSE or WebSockets: use `wait_for` with a selector, never rely on `networkidle`

**Actions**: The rendering pipeline uses Playwright. Actions in the script map to Playwright `page` methods — use whatever method fits the interaction:
- `goto` or `navigate` — load a URL
- `click` — click an element
- `fill` — type into an input
- `hover` — hover over an element
- `scroll` — scroll the viewport
- `wait` — no action, narration only
- Any other Playwright `page` method works too (`select_option`, `press`, `check`, etc.)

**SPA navigation**: For single-page applications (React, Vue, etc.), use `goto` only for the first navigation. For subsequent pages, click a nav link to use the client-side router — this avoids loading skeletons appearing in the video.

**Pacing** (`pause_after_ms` values):
- After navigation: 1000-1500ms (page needs to render)
- After visual changes the viewer needs to absorb: 1500-2500ms
- Simple waits or transitions: 500-1000ms
- The actual segment duration is `max(audio_duration, pause_after_ms)`, so narration length also affects pacing

## Phase 4: Produce the Script JSON

Read the schema and examples:

```
${CLAUDE_SKILL_DIR}/references/REFERENCE.md
```

Write the JSON script to a file. Suggest `demo-script.json` in the project root, or ask the user where they'd like it.

The script has this structure:

```json
{
  "title": "Demo Title",
  "resolution": { "width": 1280, "height": 720 },
  "segments": [
    {
      "narration": "Text spoken by TTS",
      "action": "goto",
      "url": "http://localhost:3000",
      "wait_for": "[data-testid='loaded']",
      "pause_after_ms": 1500
    }
  ]
}
```

## Phase 5: Validate and Render

Before rendering, verify the script will work.

**URL reachability**: For each `goto`/`navigate` segment, check the URL is reachable:
```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000
```

**Selector verification**: Write and run a quick Python script using Playwright that:
1. Launches a browser
2. Navigates to each URL in the script
3. Checks that each selector exists on the page via `page.query_selector()`
4. Reports any missing selectors

**Data check**: Confirm the pages show real content, not empty states.

**Checkpoint — STOP and wait for user input**: Report validation results. If everything passes, use `AskUserQuestion` to ask if the user wants to render now or tweak the script first. Show the render command:

```bash
instantdemo render demo-script.json --tts kokoro -o demo.mp4
```

Available TTS providers:
- `--tts kokoro` — Kokoro local TTS (recommended, no API keys needed, high quality, fast). Options: `--kokoro-voice af_heart` (default), `--kokoro-speed 1.0`
- `--tts google` — Google Cloud WaveNet (requires `GCP_PROJECT` in `.env` + `gcloud auth login`)
- `--tts elevenlabs` — ElevenLabs (requires `ELEVENLABS_API_KEY` + `ELEVENLABS_VOICE_ID` in `.env`)
- `--tts piper` — Piper local TTS (requires `--piper-model /path/to/model.onnx`)

Let the user decide when to run the render. They may want to tweak the script first.
