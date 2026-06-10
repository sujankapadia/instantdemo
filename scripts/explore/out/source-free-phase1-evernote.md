<!-- source-free phase1 prototype | url: http://127.0.0.1:8001/ | cost: $0.189 | wall: 109s | turns: 7 -->

Exploration complete. Here's the full picture:

# Evernote Local Viewer — App Analysis

## What the app does
A local, single-page web app for browsing Evernote ENEX exports privately. Tagline: *"Import your ENEX exports, keep notes local, and browse them with fast, private storage."* Notes are imported from `.enex` files into local storage and served via a small JSON API (`/api/notes`, `/api/notes/{id}`).

## Main screens / UI regions (single page, no routes)
- **Sidebar — Filters**: collapsible (⇔ toggle) with:
  - **Search box** (`Search title or text`) — live full-text filter (e.g. typing "Marketing" narrows 500 → 46 notes)
  - **Views**: 📄 All notes / 📎 Attachments (Attachments view filters to notes with attachments — currently 1 note)
  - **Sources**: filter by export file (`evernote-skapadia-export-1.enex` … `-5.enex`)
  - **Import ENEX** button + hidden file input (⚠️ data-mutating — avoid in demo)
- **Notes list (middle)**: 500 notes, each showing title, updated date, and source file; sorted newest-first. Items are `article.note-item`; clicking one marks it `active` and loads the detail.
- **Reader pane (right)**: shows "Select a note" until a note is clicked; then renders title, Created/Updated dates, source file, and the full note body (rendered ENML/HTML).

## Access
- URL: `http://127.0.0.1:8001/` — no login/auth wall
- All client-side; detail loads via `GET /api/notes/{id}` (no URL change on click — SPA)

## Demo-relevant details (for the requested flow)
1. **Intro**: explain the page using the header copy + sidebar features above.
2. **Scroll the Notes list**: the list scrolls within the page; **"Marketing"** is the **6th item from the top** (Updated 8/1/2023 • evernote-skapadia-export-1.enex), so only a short scroll is needed. Note: there are similar-looking entries (e.g. two "James Kirkpatrick Annual Review") — match the exact title "Marketing".
3. **Click "Marketing"** (note id 6): the reader pane shows:
   - Header: *Marketing — Created 8/1/2023 • Updated 8/1/2023 • Source evernote-skapadia-export-1.enex*
   - Body begins: *"What am I trying to achieve here? I want to be able to run experiments, so we can generate more leads…"* followed by paragraphs about trying newsletters, webinars, Medium posts, CTAs, and frustrations about pushback on ideas.

**Pre-demo checklist**
- App running on port 8001 and `/api/notes` returns data
- Notes list shows **"500 notes"** and all 5 ENEX sources are listed
- "Marketing" note exists near the top of the list and `GET /api/notes/6` returns its content
- Do **not** touch the "Import ENEX" button (file upload / data mutation)

**Playwright tips for the demo script**: don't wait for `networkidle`; use `wait_for_selector('.note-item')`. Find the Marketing item via `.note-item` titles, `scroll_into_view_if_needed()`, then `click()` — the item gains class `active` and the reader pane populates within ~1s.
