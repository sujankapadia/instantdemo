<!-- source-free phase1 prototype | url: http://127.0.0.1:8001/ | docs: scripts/explore/out/onepager-evernote.md | cost: $0.182 | wall: 64s | turns: 7 -->

The full demo flow works end-to-end. Here's the summary:

# Evernote Local Viewer — App Analysis

## What the app does
A privacy-first, single-page viewer for Evernote ENEX exports at **http://127.0.0.1:8001/** (no login, no auth wall). Notes are stored locally; the page tagline reads *"Import your ENEX exports, keep notes local, and browse them with fast, private storage."* This matches the product docs.

## Layout (one screen, three panels)
It's a single-route SPA — no separate pages, all interaction happens in a 3-column layout:

1. **Sidebar (Filters)** — collapsible (⇔ toggle). Contains:
   - **Search** box ("Search title or text") → hits `/api/search?q=…`, debounced
   - **Views**: "All notes" 📄 and "Attachments" 📎 (notes with attachments only)
   - **Sources** dropdown — filter by originating ENEX file
   - **Import ENEX** button (file upload — *do not touch during demo*)
2. **Notes list (middle)** — scrollable list with a count pill ("500 notes"). Each item shows title, Updated/Created date, and source file. Sorted by last-modified, newest first.
3. **Detail pane (right)** — shows the selected note's title, Created/Updated/Source metadata line, full rendered HTML content, tags, and downloadable attachment links when present.

## API surface observed
- `GET /api/notes` — full list; `GET /api/notes/{id}` — note detail with HTML, tags, resources
- `GET /api/search?q=` — search; `GET /api/notes/{id}/attachments/{rid}` — attachment download
- `POST /api/import/upload` — ENEX import (mutating; avoid)

## Demo-relevant details
- **Data is loaded**: 500 notes, all from source `evernote-skapadia-export-1.enex`.
- **The "Marketing" note exists** — it's the **6th item** in the list (Updated 8/1/2023), so only a short scroll is needed. ⚠️ There are other notes containing "Marketing"-adjacent titles, so match the exact title; clicking the first `.note-item` with text "Marketing" works.
- **Clicking it works**: detail pane shows title *Marketing*, meta *"Created 8/1/2023 • Updated 8/1/2023 • Source evernote-skapadia-export-1.enex"*, and full body text beginning *"What am I trying to achieve here? I want to be able to run experiments, so we can generate more leads…"*. No tags, no attachments on this note.
- Clicked list items get a green highlight (`active` class) — good visual feedback for recording.
- One minor doc discrepancy: the docs say search covers "titles and metadata," but the UI placeholder says "Search title or text" — the live app suggests body text is searched too.

### Pre-demo checklist
- App responding on port 8001 ✅
- Notes list populated (500 notes) — if empty, an ENEX import would be needed first
- "Marketing" note present near the top of the list ✅

**Suggested demo flow**: load page → point out the three panels and sidebar features (search, views, source filter, import) → scroll the Notes list to "Marketing" → click it → read the rendered note content in the detail pane.
