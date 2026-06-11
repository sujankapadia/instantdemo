"""Structured intent for a demo project.

`intent.json` lives in the project root alongside `demo-script.json`.
It captures the user's intent for generating the demo: what to show
(`goal`), who the audience is, what tone to target, what areas to
focus on or exclude, and any free-form `addenda`.

(A `length` field existed until 2026-06-11; it was removed because
nothing measured the rendered duration against it — DESIGN.md
principle 11. Loaders ignore it in old intent.json files; a length
wish in free text reaches the planner via goal/addenda just as
effectively.)

Phase 1 reads `goal`, `focus`, `excludes` to scope the codebase
analysis. Phase 2 reads all fields to shape the narrative. Phases
3-5 are mechanical translations that don't read intent.

Both the GUI's New Project flow and the future voice-input path
(#11) write intent here. The hint UI and voice are two channels
into the same data structure.

Legacy projects (created before this module existed) have a
`describe` string in state.json. When `intent.json` is missing,
callers should synthesize one via `synthesize_from_describe` —
populates `goal` from `describe` and leaves the rest empty.
Synthesized intents aren't persisted until the user actually
edits them.

See issue #39.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


INTENT_FILENAME = "intent.json"


@dataclass
class Intent:
    """Structured intent for a demo project.

    All fields default to empty / None. Only `goal` is generally
    expected to be non-empty; the rest are optional refinements.
    """

    goal: str = ""
    audience: str | None = None
    tone: str | None = None
    focus: list[str] = field(default_factory=list)
    excludes: list[str] = field(default_factory=list)
    addenda: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        """True when no field has been populated."""
        return (
            not self.goal
            and self.audience is None
            and self.tone is None
            and not self.focus
            and not self.excludes
            and not self.addenda
        )


def intent_path(project_dir: Path) -> Path:
    return project_dir / INTENT_FILENAME


def load(project_dir: Path) -> Intent | None:
    """Read intent.json. Returns None if the file doesn't exist.

    Callers can fall back to `synthesize_from_describe` when this
    returns None.
    """
    path = intent_path(project_dir)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    return Intent(
        goal=raw.get("goal", "") or "",
        audience=raw.get("audience"),
        tone=raw.get("tone"),
        focus=list(raw.get("focus") or []),
        excludes=list(raw.get("excludes") or []),
        addenda=list(raw.get("addenda") or []),
    )


def save(project_dir: Path, intent: Intent) -> None:
    """Write intent.json. Overwrites any existing file."""
    path = intent_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(intent), indent=2) + "\n")


def synthesize_from_describe(describe: str | None) -> Intent:
    """Build a default Intent from a legacy `describe` string.

    Used when loading a project that has `describe` in state.json but
    no intent.json yet. The synthesized intent isn't persisted to disk
    here — callers should only save when the user has actually edited.
    """
    return Intent(goal=(describe or "").strip())


def load_or_synthesize(project_dir: Path, describe: str | None) -> Intent:
    """Convenience: load intent.json, or synthesize from `describe`.

    Always returns an Intent (never None). Doesn't persist the
    synthesized version — that's the caller's choice once the user
    edits.
    """
    loaded = load(project_dir)
    if loaded is not None:
        return loaded
    return synthesize_from_describe(describe)
