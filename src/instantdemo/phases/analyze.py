"""Phase 1 — Understand the product.

Real implementation (Agent SDK call) lands in a later commit. For now
this is a stub that writes a placeholder artifact so the end-to-end CLI
flow is testable.
"""

from __future__ import annotations

from . import Context


STUB_BODY = """\
# Phase 1 — Codebase Analysis (stub)

This file will hold the agent's understanding of the application:
purpose, main routes/screens, seed data, and how to access the app.

Real Phase 1 lands when the Agent SDK runner is wired up.

<!-- ANSWER THESE BEFORE CONTINUING -->
flow:
url: {url}
seed_data_ready: yes
<!-- /ANSWER -->
"""


def run(context: Context) -> None:
    artifact = context.phase_artifact(1)
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(STUB_BODY.format(url=context.url))
    print(f"Phase 1 (stub) wrote {artifact}")
