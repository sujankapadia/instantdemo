<!-- source-free phase1 prototype | url: http://localhost:8000 | docs: scripts/explore/out/onepager-cca.md | cost: $0.166 | wall: 74s | turns: 5 -->

I've explored the live app. Here's the summary:

## Claude Code Analytics — App Survey

### What it does
Matches the product docs: a local analytics tool that archives Claude Code conversations and exposes dashboards, search, transcripts, and a live view of currently running sessions. Runs at **http://localhost:8000**, no login/auth wall.

### Main screens (left sidebar nav)
- **Dashboard** (`/`) — Activity chart (last 90 days), Messages chart (last 30 days), and a Projects list with session counts (~90 projects, e.g. `jellico-prototyping` 288, `showcase` 279).
- **Active** (`/active`) — **Active Sessions** page; live cards for sessions running right now.
- **Sessions** (`/sessions`) — browsable past-session transcripts, filterable by `?project_id=...`.
- **Bookmarks** (`/bookmarks`) — saved messages.
- **Search** (`/search`) — cross-conversation search.
- **Analytics** (`/analytics`) — usage analytics.
- **Analysis** (`/analysis`) — AI-powered insights/analyses.
- **Import** (`/import`) — session import (avoid triggering in a demo — mutating).
- Also: command palette (⌘K) and a sidebar toggle in the header.

### Demo-relevant details: Active Sessions flow

**The page** (`/active`): header reads "Active Sessions" with a **"5 active"** count badge and a "Running now" section. Each session renders as a card showing:
- **Project name** (e.g. `brainstack`, `vanguard`, `predictionmarketpulse`, `jellico-reports`, `instantdemo`)
- **Session age/duration** (e.g. "199h 40m", "1h 52m")
- **"Recent messages"** — the last few user prompts, verbatim
- **Terminal info** — TTY and PID (e.g. `ttys003`, `PID 8100`)

**Click-through**: each card is a link to `/sessions/{uuid}` — the full session detail page. Verified with the `jellico-reports` card → `/sessions/ee89929c-...`, which shows:
- Stats strip: **Messages (880), Tool Uses (220), Tokens (226.5k), Active Time (387m), User Text, Assistant Text**
- Full transcript with **All / User / Assistant** filter tabs, timestamped messages, expandable tool-use entries (Read/Edit with file paths), and per-message token counts
- A live token in/out footer ("1.3k in / 225.1k out") — the page appears to stream/update for active sessions

### Pre-demo checklist
1. App is up on port 8000 (no auth needed).
2. **At least one Claude Code session is actually running** — the Active page is empty otherwise. Currently 5 are active; counts/durations change in real time.
3. Pick a card with meaningful "Recent messages" text (e.g. `jellico-reports` or `instantdemo`) for the click-through.
4. Session UUIDs are ephemeral — click the card live rather than hardcoding a URL.
5. Pages use live updates; in any automation, wait on selectors, not `networkidle`.

**Doc discrepancies**: none material — live app matches the one-pager. One nuance: the docs say "jump into any of them," which in practice means opening the session's transcript view in the app (not attaching to the terminal).
