<!-- source-free phase1 prototype | url: http://localhost:8000 | docs: /Users/skapadia/dev/personal/claude-code-analytics/README.md | cost: $0.177 | wall: 70s | turns: 5 -->

App is up. Now let me focus on the demo-relevant screen: `/active`.
Exploration complete. Here's the summary:

# Claude Code Analytics — Live App Findings

## What the app does
Claude Code Analytics (running at **http://localhost:8000**, no login/auth) is a local dashboard that captures, archives, and analyzes Claude Code conversations. The live app matches the README closely: a React SPA with sidebar navigation, a ⌘K command palette, and a projects list (90+ projects, with session counts).

## Main screens (top nav)
- **Dashboard (`/`)** — KPI cards, "Activity (last 90 days)" chart, "Messages (last 30 days)", and a Projects table.
- **Active (`/active`)** — Live view of currently running Claude Code sessions (the demo target).
- **Sessions (`/sessions`)** — Searchable session list with detail pane; filterable by `project_id`.
- **Bookmarks, Search, Analytics, Analysis, Import** — as documented. ⚠️ Note: the nav label is "**Active**", not "Active Sessions" (the page H1 is "Active Sessions"); there's also an **Import** nav item the README doesn't list as a page.

## Demo-relevant details: Active Sessions flow

**1. The page (`/active`)** — Header reads "**Active Sessions — 5 active — Running now**". It renders one **card per running session**, each showing:
- **Project name** (e.g. `brainstack`, `vanguard`, `predictionmarketpulse`, `jellico-reports`, `instantdemo`)
- **Session duration/age** (e.g. "199h 31m", "1h 42m")
- **"Recent messages"** — the last ~3 user prompts from that session, verbatim
- **Terminal TTY and PID** (e.g. `ttys003 / PID 8100`) — it's detecting live OS processes

**2. Click-through** — Each card is a link to the session detail page at `/sessions/<uuid>`. Clicking the first card (brainstack) lands on `/sessions/034d7d3d-...`, which shows:
- **Stat cards**: Messages (4,124), Tool Uses (929), Tokens (4.1M), Active Time (1,472m), User Text / Assistant Text character counts
- **Conversation viewer** with role filter tabs (All / User / Assistant), timestamps, per-message token counts, and full message content (virtual scrolling)

**3. Talking points for the demo**: Active Sessions answers "what's running right now across all my terminals?" — project, how long it's been going, what was last asked, and which terminal/PID it lives in — then one click drops you into the full transcript and stats for that session.

## Pre-demo checklist
- ✅ App is up on port 8000; no auth wall.
- ⚠️ **At least one Claude Code session must actually be running** — the page reflects live processes. Right now there are 5 (good demo material). If all sessions exit, the page would presumably show empty state.
- ⚠️ Card content shows **real user prompts verbatim** (currently includes work content mentioning client/colleague names, e.g. Vanguard, "send PTO report to Gregg"). Review for anything sensitive before recording, or pick a card with neutral content (`brainstack` or `instantdemo` look safest).
- The page updates live (SSE) — counts/messages may shift mid-demo; don't rely on exact numbers.
