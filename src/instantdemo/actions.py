"""The canonical demo-script action contract.

Single source of truth for which segment `action` values exist and
which fields each one requires. Used by:

  - Phase 5 (`phases/script.py`) to validate the agent-emitted
    demo-script.json at build time — an unknown action fails in
    seconds, with a correction round-trip to the agent, instead of
    mid-recording in Phase 6 where it costs the whole take.
  - The renderer (`render.py`) to pre-validate all segments before
    TTS or recording starts (hand-edited scripts don't pass through
    Phase 5), and to keep `_ACTION_FIELD_MAP` honest via the module
    self-check below.

Lives in its own module (not render.py) because the renderer imports
Playwright at module level and Phase 5 must stay importable without
optional heavy deps — see `phases.get_phase_runner`'s lazy-import
rationale.

History: the Phase 5 prompt used to define `action` as "a Playwright
page method name", and the renderer had a `getattr(page, action)`
fallback to match. The fallback stripped schema fields from kwargs,
so any improvised method needing `selector`/`url`/etc. crashed
mid-recording (first hit: a source-free run emitted
`wait_for_selector`). The action set is now closed.
"""

from __future__ import annotations


# action -> fields a segment with that action must carry.
# `narration` and `pause_after_ms` are segment-level, not per-action.
CANONICAL_ACTIONS: dict[str, frozenset[str]] = {
    "navigate": frozenset({"url"}),
    "goto": frozenset({"url"}),
    "click": frozenset({"selector"}),
    "fill": frozenset({"selector", "value"}),
    "hover": frozenset({"selector"}),
    "scroll": frozenset(),  # optional: pixels (default 300)
    "wait": frozenset(),
    "select_option": frozenset({"selector", "value"}),
    "press": frozenset({"selector", "key"}),
    "check": frozenset({"selector"}),
    "uncheck": frozenset({"selector"}),
    "evaluate": frozenset({"expression"}),
}


def validate_segments(segments: list[dict]) -> list[str]:
    """Validate segment actions against the canonical contract.

    Returns a list of human-readable problems (empty = valid).
    Indexes are 1-based to match the artifact numbering users see.
    """
    problems: list[str] = []
    for i, seg in enumerate(segments, start=1):
        action = seg.get("action")
        if action not in CANONICAL_ACTIONS:
            problems.append(
                f"segment {i}: unknown action {action!r}; "
                f"allowed actions: {', '.join(sorted(CANONICAL_ACTIONS))}"
            )
            continue
        for field in CANONICAL_ACTIONS[action]:
            if not seg.get(field):
                problems.append(
                    f"segment {i}: action {action!r} requires the "
                    f"{field!r} field"
                )
    return problems
