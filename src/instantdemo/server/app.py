"""FastAPI app for the InstantDemo GUI."""

from __future__ import annotations

from contextlib import asynccontextmanager
from importlib.resources import files
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .routes import project, runs


_NOT_BUILT_HTML = """\
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>InstantDemo — frontend not built</title>
  <style>
    body { font-family: -apple-system, system-ui, sans-serif; padding: 3rem;
           max-width: 720px; margin: 0 auto; color: #222; }
    code { background: #f4f4f4; padding: 2px 6px; border-radius: 4px; }
    pre  { background: #f4f4f4; padding: 1rem; border-radius: 6px; overflow-x: auto; }
    h1   { margin-top: 0; }
  </style>
</head>
<body>
  <h1>Frontend not built</h1>
  <p>The InstantDemo GUI server is running, but the frontend bundle is
     missing. The API works (try <code>/api/health</code>), but the UI
     can't load.</p>
  <p>If you installed from a source checkout, build the frontend:</p>
  <pre>./scripts/build_gui.sh</pre>
  <p>Or run the Vite dev server (in a separate terminal) and open
     <code>http://localhost:5173</code>:</p>
  <pre>cd frontend &amp;&amp; npm install &amp;&amp; npm run dev</pre>
  <p>If you installed from a wheel, please file a bug — the wheel
     should have shipped with the bundle.</p>
</body>
</html>
"""


def _web_dir() -> Path:
    """Return the path to the bundled frontend assets, regardless of how
    the package was installed (editable, wheel, zipapp)."""
    return Path(str(files("instantdemo").joinpath("server", "web")))


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """FastAPI lifespan that owns the long-lived RunManager (and
    therefore the ClaudeSDKClient) across the app's lifetime."""
    app.state.run_manager = runs.RunManager()
    try:
        yield
    finally:
        manager = getattr(app.state, "run_manager", None)
        if manager is not None:
            await manager.shutdown()


def create_app() -> FastAPI:
    app = FastAPI(title="InstantDemo", version="0.1.0", lifespan=_lifespan)

    # In dev, the Vite dev server runs on a different port and proxies
    # /api/* to us. The proxy avoids cross-origin requests entirely, but
    # CORS is enabled for localhost during dev as belt-and-suspenders.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, bool]:
        return {"ok": True}

    app.include_router(project.router)
    app.include_router(runs.router)

    web_dir = _web_dir()
    index_html = web_dir / "index.html"

    if index_html.exists():
        # Serve the built SPA. `html=True` serves index.html for
        # directory paths (e.g. "/").
        app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="web")
    else:
        # Helpful fallback for source checkouts where the bundle
        # hasn't been built yet. Keeps the API usable.
        @app.get("/", response_class=HTMLResponse)
        def _not_built() -> str:
            return _NOT_BUILT_HTML

    return app


app = create_app()
