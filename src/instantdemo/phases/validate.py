"""Phase 5 — Validate the script and invoke the renderer.

Stub. Real implementation will:
  - Use the Agent SDK to validate URLs (curl) and selectors (Playwright probe)
  - Then call the renderer via `instantdemo render` (or render.main directly)

For now the stub just verifies the script artifact exists.
"""

from __future__ import annotations

from . import Context


def run(context: Context) -> None:
    script = context.phase_artifact(4)
    if not script.exists():
        raise RuntimeError(
            f"Demo script missing at {script}. Run phase 4 first."
        )
    print(
        f"Phase 5 (stub) would validate {script} "
        f"and render to {context.output} via TTS={context.tts!r}."
    )
