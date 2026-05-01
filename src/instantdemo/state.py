"""Read/write `.instantdemo/state.json`.

The state file records what happened during a `generate` run:
  - session_id, url, describe (the inputs)
  - per-phase status, timestamps, and any extras (cost, num_turns, ...)
    populated by Task #15 (metrics) once the real phase runners exist.

Schema (illustrative):

    {
      "session_id": "uuid4-string",
      "url": "http://localhost:3000",
      "describe": "show the signup flow",
      "created_at": "2026-05-01T...",
      "phases": {
        "1": {"status": "completed", "started_at": "...", "completed_at": "...",
              "cost_usd": 0.18, "duration_ms": 44500, "num_turns": 19},
        "2": {"status": "in_progress", "started_at": "..."},
        "3": {"status": "pending"}
      }
    }

State is best-effort: if the user kills the CLI mid-phase, the next run
sees that phase as "in_progress" and the user can decide whether to
resume (`--from-phase N`) or restart. We never delete state here — that's
a deliberate choice; users can `rm .instantdemo/state.json` if they want
a clean slate.
"""

from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

STATE_FILENAME = "state.json"


def _state_path(state_dir: Path) -> Path:
    return state_dir / STATE_FILENAME


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load(state_dir: Path) -> dict:
    """Load state from disk, or return a fresh skeleton if absent."""
    path = _state_path(state_dir)
    if not path.exists():
        return {
            "session_id": str(uuid.uuid4()),
            "url": None,
            "describe": None,
            "created_at": _now(),
            "phases": {},
        }
    return json.loads(path.read_text())


def save(state_dir: Path, state: dict) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    _state_path(state_dir).write_text(json.dumps(state, indent=2) + "\n")


def update_inputs(state: dict, *, url: str, describe: str | None) -> dict:
    """Set the run-level inputs on first run, leave alone on resume."""
    if state.get("url") is None:
        state["url"] = url
    if state.get("describe") is None and describe is not None:
        state["describe"] = describe
    return state


def record_phase_metrics(state_dir: Path, phase_number: int, **metrics) -> None:
    """Merge arbitrary metric fields into a phase's state entry.

    Used by phase runners after a query() finishes to stash
    cost / duration / num_turns / session_id_phase. Kept SDK-agnostic
    (the caller pulls fields off ResultMessage).
    """
    s = load(state_dir)
    entry = s.setdefault("phases", {}).setdefault(str(phase_number), {})
    entry.update(metrics)
    save(state_dir, s)


@contextmanager
def phase_run(state_dir: Path, phase_number: int) -> Iterator[dict]:
    """Bracket a phase's execution: mark started_at, then completed_at on
    success. On failure, mark status=error and re-raise.

    Yields the phase entry dict so the caller can stash extras (e.g.,
    metrics from a ResultMessage) before exit.
    """
    state = load(state_dir)
    key = str(phase_number)
    entry = state.setdefault("phases", {}).setdefault(key, {})
    entry["status"] = "in_progress"
    entry["started_at"] = _now()
    save(state_dir, state)

    try:
        yield entry
    except BaseException:
        # Re-load to avoid clobbering anything the runner wrote, then mark
        # the failure timestamp.
        state = load(state_dir)
        state.setdefault("phases", {}).setdefault(key, entry)
        state["phases"][key]["status"] = "error"
        state["phases"][key]["errored_at"] = _now()
        save(state_dir, state)
        raise

    state = load(state_dir)
    merged = state.setdefault("phases", {}).setdefault(key, {})
    merged.update(entry)  # carry forward any extras the caller added
    merged["status"] = "completed"
    merged["completed_at"] = _now()
    save(state_dir, state)
