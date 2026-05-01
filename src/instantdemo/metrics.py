"""Append per-phase ResultMessage metrics to `.instantdemo/metrics.jsonl`.

state.json records the *current* state of each phase (one entry per
phase, overwritten on re-runs). metrics.jsonl is the *history* — one
JSON line per phase per run, append-only. Useful for:

  - Costing: averaging $/render over many runs informs a hosted-version
    pricing model.
  - Variance tracking: how stable are the agent's costs and durations?
  - Cache effectiveness: how much do cache reads dominate over fresh
    creations as you iterate against the same codebase?

Schema (one line per phase per run):

    {
      "timestamp": "2026-05-01T15:30:00+00:00",
      "run_session_id": "<state.json session_id — groups rows by run>",
      "phase_session_id": "<ResultMessage.session_id — the SDK conversation>",
      "phase_number": 1,
      "phase_name": "analyze",
      "is_error": false,
      "stop_reason": "end_turn",
      "cost_usd": 0.18,
      "duration_ms": 44500,
      "duration_api_ms": 43600,
      "num_turns": 19,
      "input_tokens": 1796,
      "output_tokens": 2739,
      "cache_creation_tokens": 26373,
      "cache_read_tokens": 123273
    }

A row only lands here on a successful agent return. Phases that crash
before producing a ResultMessage don't contribute a row — they show
up as `status: "error"` in state.json instead.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

METRICS_FILENAME = "metrics.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def append(state_dir: Path, **fields) -> None:
    """Append one JSON line to `.instantdemo/metrics.jsonl`.

    A `timestamp` is added automatically if not provided.
    """
    state_dir.mkdir(parents=True, exist_ok=True)
    fields.setdefault("timestamp", _now())
    line = json.dumps(fields, default=str)
    with (state_dir / METRICS_FILENAME).open("a", encoding="utf-8") as f:
        f.write(line + "\n")
