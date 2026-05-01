"""Phase 4 — Produce the demo-script.json.

Stub. Real implementation will use the Agent SDK with Write tool only,
producing a JSON script that conforms to the schema.
"""

from __future__ import annotations

import json

from . import Context


STUB_SCRIPT = {
    "_stub": True,
    "_note": (
        "This is a placeholder demo-script.json written by the Phase 4 stub. "
        "Real Phase 4 lands when the Agent SDK runner is wired up."
    ),
    "title": "Stub Demo",
    "resolution": {"width": 1280, "height": 720},
    "segments": [],
}


def run(context: Context) -> None:
    phase3 = context.phase_artifact(3)
    if not phase3.exists():
        raise RuntimeError(
            f"Phase 3 artifact missing at {phase3}. Run phase 3 first."
        )
    artifact = context.phase_artifact(4)  # demo-script.json in source root
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(json.dumps(STUB_SCRIPT, indent=2) + "\n")
    print(f"Phase 4 (stub) wrote {artifact}")
