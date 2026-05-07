"""FastAPI app for the InstantDemo GUI."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import project


def create_app() -> FastAPI:
    app = FastAPI(title="InstantDemo", version="0.1.0")

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

    return app


app = create_app()
