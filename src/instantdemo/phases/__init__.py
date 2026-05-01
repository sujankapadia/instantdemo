"""Phase runners for the InstantDemo workflow.

The five phases mirror the source skill's structure (SKILL.md):

    1. analyze   — Understand the product
    2. narrate   — Plan the narrative
    3. gather    — Gather technical details (selectors, waits, pacing)
    4. script    — Produce the demo-script.json
    5. validate  — Validate the script and invoke the renderer

Each phase is implemented as a module with a `run(context)` function that
reads any prior-phase artifacts from the state directory, does its work,
and writes a single artifact back to the state directory. Phase 4 writes
the user-facing demo-script.json instead of a state-dir artifact, and
Phase 5 invokes the renderer (no artifact of its own).

Today every phase is stubbed — it writes a placeholder file so the
end-to-end CLI flow is testable before any AI calls are wired in. The
real implementations land in subsequent commits (per CLI-DESIGN.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PHASES = ("analyze", "narrate", "gather", "script", "validate")
"""Phase names in execution order, indexed by 1-based phase number."""

PHASE_NUMBERS = {name: i + 1 for i, name in enumerate(PHASES)}


@dataclass
class Context:
    """Inputs and resolved paths shared across phases.

    Built once by the CLI and passed to each phase's `run()` function.
    """

    url: str
    source: Path                # codebase root (the user's project)
    describe: str | None        # optional — like the skill's $ARGUMENTS
    state_dir: Path             # source / ".instantdemo"
    output: Path                # final MP4 path (used by phase 5)
    tts: str                    # TTS provider name (used by phase 5)
    no_edit: bool               # if True, skip $EDITOR checkpoints

    @property
    def script_path(self) -> Path:
        """Path to the user-facing demo-script.json (Phase 4 output)."""
        return self.source / "demo-script.json"

    def phase_artifact(self, phase_number: int) -> Path:
        """Resolve the per-phase artifact path within the state dir."""
        if phase_number == 4:
            return self.script_path
        return self.state_dir / f"phase{phase_number}.md"


def phase_number_from_name(name: str) -> int:
    """Translate a phase name (e.g. 'analyze') to its 1-based number."""
    if name not in PHASE_NUMBERS:
        raise ValueError(f"Unknown phase: {name!r}. Valid: {', '.join(PHASES)}")
    return PHASE_NUMBERS[name]


def phase_name_from_number(number: int) -> str:
    """Translate a 1-based phase number to its name."""
    if not 1 <= number <= len(PHASES):
        raise ValueError(f"Invalid phase number {number}; must be 1..{len(PHASES)}")
    return PHASES[number - 1]
