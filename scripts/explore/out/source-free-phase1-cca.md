<!-- source-free phase1 prototype | url: http://localhost:8000 | cost: $0.211 | wall: 111s | turns: 8 -->

Exploration complete. Here's the full report.

# Claude Code Analytics — App Analysis

## What the app does
**Claude Code Analytics** (title: "Claude Code Analytics", `http://localhost:8000`) is a local dashboard that imports Claude Code conversation transcripts from `~/.claude/projects/` into a database and provides browsing, search, and analytics over them — 110 projects, ~1,204 sessions, 153.5k messages, 29.7M tokens in the current dataset. A file watcher keeps it synced with live Claude Code activity in real time.

## Main screens
| Route | What it renders |
|---|---|
| `/` Dashboard | Stat cards (Projects, Sessions, Messages, Tokens, Active Time), 90-day activity heatmap, 30-day message volume, per-project stats table |
| `/active` | **Active Sessions** — live cards for Claude Code sessions running right now |
| `/sessions` | Full session list (filterable by project via sidebar), each row showing first prompt, project, date, msg/tool counts, duration |
| `/bookmarks` | Saved/bookmarked messages with notes and "View" links back into sessions |
| `/search` | Full-text search with filters: All / Messages / Tool Inputs / Tool Results / Sessions |
| `/analytics` | Charts: daily messages, token usage, activity heatmap, messages & active time by project, with time-range tabs |
| `/analysis` | AI analysis runner — pick project/session/analysis type (e.g. "decisions") and run extraction |
| `/import` | Explains the automatic file watcher; "Run Full Import" button for manual rescan |

A persistent left sidebar lists all projects with session counts; ⌘K opens a command palette.

## Access
- `http://localhost:8000`, **no login/auth wall** — page loads directly.
- Pages render server-side quickly; the Active page appears to use live data (avoid `networkidle` waits — use `domcontentloaded` + selector waits).

## Demo-relevant details (Active Sessions flow)

**The `/active` page** — heading "Active Sessions" with a badge showing the count ("5 active") and a "Running now" section. Each active session is a **clickable card** (`main a` elements) showing:
- Project name (h3) — currently: brainstack, vanguard, predictionmarketpulse, jellico-reports, instantdemo
- Session duration (e.g. "1h 3m", "198h 51m")
- "Recent messages" — the last few user prompts, verbatim
- Terminal/process info: tty (e.g. `ttys007`) and PID — i.e., it's detecting actual running Claude Code processes

**Click-through**: each card links to `/sessions/{uuid}`. The session detail page shows:
- Breadcrumb `Sessions / {short-id}` and stat cards: Messages, Tool Uses, Tokens, Active Time, User/Assistant char counts
- A full message transcript with **All / User / Assistant filter buttons**, timestamps, per-message token counts, and expandable tool-use entries (e.g. `Read jellico-reports/CLAUDE.md`, `Edit reports/revenue_report.py`)
- A running token footer ("Tokens: 1.3k in / 225.1k out")

**Good demo pick**: the **jellico-reports** session (`/sessions/ee89929c-...`) — short (1h), readable narrative (reading CLAUDE.md, updating a revenue report), 880 messages / 220 tool uses. The instantdemo card's preview text is raw `<task-notification>` markup — less photogenic.

**Pre-demo checklist:**
1. ✅ App responding on port 8000 (no auth)
2. ⚠️ **At least one Claude Code session must actually be running** — the Active page detects live processes (tty/PID). If nothing is running, the page will presumably show zero active sessions. Verify the "N active" badge > 0 before recording.
3. ⚠️ Active session set is volatile — durations/recent-messages change between takes; re-verify which card you'll click just before recording.
4. Note: session detail pages have **no `<h1>`** — automation should wait on the breadcrumb or stat cards, not a heading.
