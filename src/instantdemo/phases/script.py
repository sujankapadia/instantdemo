"""Phase 5 — Build the demo-script.json. DETERMINISTIC (no agent).

Projects the verified storyboard to the demo-script.json shape the
renderer consumes (storyboard.to_demo_script). Every field the
renderer needs was resolved by Phase 3 (selector hypothesis) and
verified/revised by Phase 4 (dress rehearsal), so translation is
pure code: instant, free, and with no agent failure modes — the
original agent-based Phase 5 once invented a non-canonical action
("wait_for_selector") that crashed the renderer mid-recording (#57).

Validation is belt-and-braces: the storyboard must validate at
stage="verified" (every scene verified or warn — Phase 4's gate),
and the projection must pass the renderer's own action contract
(actions.validate_segments). A projection failure after a passing
storyboard validation is a bug in the projection, not bad input,
and raises loudly.

demo-script.json remains the unchanged render contract: render.py,
the GUI segment endpoints, and hand-editing workflows are untouched.
"""

from __future__ import annotations

import json
import time

from .. import metrics as _metrics
from .. import state
from .. import storyboard
from ..actions import validate_segments
from . import Context, phase_name_from_number


async def run(context: Context) -> None:
    start = time.monotonic()

    doc = storyboard.load(context.state_dir)
    problems = storyboard.validate_storyboard(doc, stage="verified")
    if problems:
        raise RuntimeError(
            "Phase 5: the storyboard is not renderable:\n"
            + "\n".join(f"  - {p}" for p in problems)
            + "\nRun Phase 4 (Explore) to verify the scenes first."
        )

    script = storyboard.to_demo_script(doc)

    # Final assertion against the renderer's own contract. This can
    # only fail on a projection bug — surface it loudly, never write
    # a script the renderer would reject.
    problems = validate_segments(script["segments"])
    if problems:
        raise RuntimeError(
            "Phase 5: projection produced an invalid script (this is a "
            "bug in storyboard.to_demo_script):\n"
            + "\n".join(f"  - {p}" for p in problems)
        )

    artifact = context.script_path
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(json.dumps(script, indent=2) + "\n")

    elapsed_ms = int((time.monotonic() - start) * 1000)
    fields = {
        "cost_usd": 0.0,
        "duration_ms": elapsed_ms,
        "num_turns": 0,
        "is_error": False,
    }
    state.record_phase_metrics(context.state_dir, 5, **fields)
    snapshot = state.load(context.state_dir)
    _metrics.append(
        context.state_dir,
        run_session_id=snapshot.get("session_id"),
        phase_number=5,
        phase_name=phase_name_from_number(5),
        **fields,
    )

    print(
        f"\nPhase 5 done — {artifact} ($0.00, {elapsed_ms / 1000:.1f}s, "
        f"deterministic projection) ({len(script['segments'])} segments)"
    )
