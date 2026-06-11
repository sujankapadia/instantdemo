# InstantDemo — Content Series

A two-part series introducing the tool and then the vision for where it's going.

## Post 1: I Built a Tool That Turns Your Codebase Into a Demo Video

**Hook:** What if you could point an AI agent at your app and get a narrated demo video back — no screen recording, no video editing, no script writing?

**Core content:**
- The problem: Recording demo videos is tedious. You write a script, record your screen, re-record when you stumble, edit out the mistakes, add narration, sync the audio. For a 60-second demo, you spend an hour.
- What InstantDemo does: It's a Claude Code skill. You run `/generate-demo`, describe what to demo, and the agent does the rest.
- The 5-phase workflow:
  1. Reads your codebase (routes, components, README) to understand what the app does
  2. Drafts a narrative — 4-8 segments covering a compelling flow
  3. Discovers stable CSS selectors and wait conditions via Playwright
  4. Produces a JSON script mapping narration to browser actions
  5. Renders the video: Playwright records the browser, TTS generates narration, ffmpeg merges them into an MP4
- The key design insight: the JSON script is the clean contract between the AI part and the rendering pipeline. It's human-readable, editable, and version-controllable. Change your UI? Edit the selectors in JSON and re-render — no re-recording.
- Checkpoints at each phase — the agent doesn't auto-proceed. You review the narrative before it writes the script, review the script before it renders.
- Show a real example: the JSON script and the resulting video.

**Why it matters:** Demo videos are one of the most effective ways to communicate what software does, and one of the most annoying to produce. This makes them regeneratable artifacts instead of one-time recordings.

## Post 2: From Claude Code Skill to Standalone Product

**Hook:** InstantDemo started as a Claude Code skill. Here's why it's becoming a standalone app — and eventually a product anyone can use.

**Core content:**

**The limitation today:** As a skill, it requires a Claude Code session. You can't distribute it, embed it in CI/CD, or give it to a product manager.

**The Agent SDK conversion:**
- The Claude Agent SDK lets you build the same agentic workflow as a standalone Python app — no Claude Code session needed
- Each phase becomes a `query()` call with targeted tools (read-only for analysis, write for script generation)
- The rendering pipeline (`render.py`) stays as-is — it's already standalone
- The result: `pip install instantdemo` — anyone with a Claude subscription can use it

**The GUI vision — the interaction spectrum:**
- Full auto: "Demo the signup flow" → agent handles everything
- Guided: Agent generates a narrative, you tweak it in a visual editor, agent fills in technical details
- Manual: Agent discovers your app's routes and interactive elements, you drag-and-drop them into a demo flow, agent resolves selectors and timing
- These aren't separate modes — you slide along the spectrum freely. Start with full auto, watch the render, drop into the editor to swap two segments.

**The visual workflow builder:**
- After codebase analysis, the app exposes discovered operations as draggable building blocks: [Navigate: /dashboard], [Click: "Create New"], [Fill: Email field]
- You compose the flow you want. The AI does discovery, the human does curation.

**Smart re-render:**
- Narration-only change? Reuse browser footage, regenerate audio, re-merge. Seconds.
- Action change? Full re-render. The app detects which strategy applies automatically.

**Who this is for beyond developers:**
- Product managers generating demo videos without touching code
- Sales teams creating custom demos per prospect by selecting which features to highlight
- Documentation teams maintaining video libraries that auto-regenerate when the UI changes

**The path: local CLI → local GUI app → hosted SaaS.** Local first validates demand before taking on infrastructure. The FastAPI backend, React frontend, and JSON script format carry through every stage.

**Ends with:** The JSON script format was always the right abstraction. It just needs a visual layer on top of it.
