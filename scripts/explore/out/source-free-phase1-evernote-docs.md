<!-- source-free phase1 prototype | url: http://127.0.0.1:8001/ | docs: /Users/skapadia/dev/personal/evernote-importer/README.MD | cost: $0.168 | wall: 75s | turns: 6 -->

The app is live on port 8001 and the "Marketing" note exists (id 6). Now let me explore the UI with Playwright.
Single-page app, all on one screen. Now the demo click-through: scroll the Notes list to "Marketing" and click it.
I have everything needed. Here's the summary:

# Evernote Local Viewer — App Analysis

## What the app does
A privacy-first, zero-cloud viewer for Evernote exports. It imports `.enex` files into a local SQLite store and serves a single-page web UI for browsing, searching, and reading your notes — everything stays on your machine.

## Access
- **URL:** `http://127.0.0.1:8001/` — ⚠️ docs say port 8000; the live app runs on **8001**
- **No login/auth wall** — the UI loads straight into the viewer
- Backend API confirmed healthy (`GET /api/health` → `{"status":"ok"}`)

## Screens / UI regions (single-page app)
Everything lives on one screen with a three-panel layout:

| Region | What it renders |
|---|---|
| **Header** | "Evernote Local Viewer" title + tagline ("Import your ENEX exports, keep notes local…") |
| **Filters sidebar** (`aside.nav-card`, collapsible via ⇔) | Search box ("Search title or text"), Views (All notes / Attachments), Sources filter (5 enex files listed), Import ENEX button |
| **Notes list** (`#note-list`) | 500 notes as `article.note-item` cards, sorted by last-updated descending; each shows title, updated date, and source file |
| **Detail pane** (`section#detail`) | "Select a note" placeholder until a note is clicked; then full note content with Created/Updated/Source metadata |

## Demo-relevant details (for the scripted flow)
1. **Explain the page**: header + tagline are visible on load; sidebar shows search, views, source filters, and import — all the talking points from the docs are visibly present.
2. **Scroll the Notes list**: the list scrolls within `#note-list`. "Marketing" is the **6th item from the top** (Updated 8/1/2023, source `evernote-skapadia-export-1.enex`) — a short, natural scroll.
3. **Click Marketing**: selector `article.note-item[data-id="6"]` (exactly one match). Clicking renders the full note in the detail pane — a memo about running marketing experiments to generate leads ("What am I trying to achieve here? I want to be able to run experiments, so we can generate more leads…"). Content is plainly readable, proving read access.
4. **Search works live**: typing "Marketing" filters to ~8 notes via full-text matching (matches body text, not just titles — the docs' claim that "UI uses metadata and filters today" is stale; live search hits note text).

## Pre-demo checklist
- ✅ Server running on port **8001** (not 8000 as docs state)
- ✅ Data imported: 500 notes across 5 enex source files
- ✅ "Marketing" note exists (id 6) with readable content, no attachments
- ⚠️ Avoid the **Import ENEX** button during the demo (data-mutating); all other interactions (scroll, click, search, view toggles) are read-only
- Note: detail pane has no separate URL — clicking a note doesn't change the route, so the demo must show the click, not deep-link
