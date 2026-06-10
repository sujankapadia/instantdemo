"""Pre-flight URL check (M1): probe the app URL the user typed into
the New Project form and hand back a screenshot + page title within
seconds — "this is the app I found, right?".

Soft gate by design: failures return ok=false with a plain-language
message and HTTP 200. The form warns but never blocks submission —
the agent retries during exploration anyway, and a transient hiccup
at form-fill time shouldn't stop the user.

Sync Playwright runs via asyncio.to_thread (the renderer's
run_in_executor lesson — sync Playwright raises if invoked on the
event-loop thread), bounded by an overall 10s wait_for.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["preflight"])

PREFLIGHT_FILENAME = "preflight.png"
_GOTO_TIMEOUT_MS = 8_000
_OVERALL_TIMEOUT_S = 10.0


class PreflightRequest(BaseModel):
    url: str


class PreflightResponse(BaseModel):
    ok: bool
    title: str | None = None
    final_url: str | None = None
    screenshot: bool = False
    error: str | None = None


def _project_state_dir() -> Path:
    override = os.environ.get("INSTANTDEMO_PROJECT_DIR")
    project = Path(override).resolve() if override else Path.cwd()
    return project / ".instantdemo"


def _probe(url: str, png_path: Path) -> tuple[str | None, str | None]:
    """Blocking Playwright probe. Returns (title, final_url); raises
    on navigation failure. Runs inside asyncio.to_thread."""
    from playwright.sync_api import sync_playwright

    png_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(
                viewport={"width": 1280, "height": 800}
            )
            page.goto(
                url, wait_until="domcontentloaded", timeout=_GOTO_TIMEOUT_MS
            )
            title = page.title()
            final_url = page.url
            page.screenshot(path=str(png_path))
            return title, final_url
        finally:
            browser.close()


@router.post("/preflight", response_model=PreflightResponse)
async def preflight(request: PreflightRequest) -> PreflightResponse:
    url = request.url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return PreflightResponse(
            ok=False,
            error="Enter a full http:// or https:// URL.",
        )

    png_path = _project_state_dir() / PREFLIGHT_FILENAME
    try:
        title, final_url = await asyncio.wait_for(
            asyncio.to_thread(_probe, url, png_path),
            timeout=_OVERALL_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        return PreflightResponse(
            ok=False,
            error=(
                "The page didn't respond within 10 seconds. Check that "
                "the app is running and the URL is right."
            ),
        )
    except Exception as e:  # noqa: BLE001 — every probe failure is a soft warning
        message = str(e).splitlines()[0][:200]
        if "ERR_CONNECTION_REFUSED" in message:
            message = "Nothing is listening at that address."
        elif "ERR_NAME_NOT_RESOLVED" in message:
            message = "That hostname doesn't resolve."
        return PreflightResponse(
            ok=False,
            error=f"Couldn't reach the app: {message}",
        )

    return PreflightResponse(
        ok=True,
        title=title or None,
        final_url=final_url,
        screenshot=png_path.exists(),
    )


@router.get("/preflight/screenshot")
def preflight_screenshot() -> FileResponse:
    path = _project_state_dir() / PREFLIGHT_FILENAME
    if not path.exists():
        raise HTTPException(status_code=404, detail="no preflight screenshot")
    return FileResponse(path=str(path), media_type="image/png")
