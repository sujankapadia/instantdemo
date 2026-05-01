"""Phase 3 — Gather technical details.

Stub. Real implementation will use the Agent SDK with read-only tools
(Read, Glob, Grep) to find selectors, wait conditions, and pacing.
"""

from __future__ import annotations

from . import Context


STUB_BODY = """\
# Phase 3 — Technical Details (stub)

This file will hold the per-segment technical details: stable selectors,
wait conditions, Playwright actions, and pacing guidance.

Real Phase 3 lands when the Agent SDK runner is wired up.
"""


def run(context: Context) -> None:
    phase2 = context.phase_artifact(2)
    if not phase2.exists():
        raise RuntimeError(
            f"Phase 2 artifact missing at {phase2}. Run phase 2 first."
        )
    artifact = context.phase_artifact(3)
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(STUB_BODY)
    print(f"Phase 3 (stub) wrote {artifact}")
