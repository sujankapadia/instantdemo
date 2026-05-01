"""Phase 2 — Plan the narrative.

Stub. Real implementation will use the Agent SDK with no tools (pure
reasoning over the Phase 1 artifact).
"""

from __future__ import annotations

from . import Context


STUB_BODY = """\
# Phase 2 — Narrative Plan (stub)

This file will hold the planned demo narrative: 4-8 segments with
draft narration text and proposed actions.

Real Phase 2 lands when the Agent SDK runner is wired up.

<!-- ANSWER THESE BEFORE CONTINUING -->
tone: casual
audience: technical
terminology:
<!-- /ANSWER -->
"""


def run(context: Context) -> None:
    phase1 = context.phase_artifact(1)
    if not phase1.exists():
        raise RuntimeError(
            f"Phase 1 artifact missing at {phase1}. Run phase 1 first."
        )
    artifact = context.phase_artifact(2)
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(STUB_BODY)
    print(f"Phase 2 (stub) wrote {artifact}")
