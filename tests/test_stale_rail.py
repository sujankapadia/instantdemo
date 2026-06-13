"""Unit tests for persisted phase staleness (M8/#85 item 4).
Spec: tests/test-specs/test_stale_rail.md."""

from __future__ import annotations

from pathlib import Path

from instantdemo import state as state_mod
from instantdemo.server.routes.runs import _mark_stale_phases


def all_completed() -> dict:
    return {str(n): {"status": "completed"} for n in range(1, 7)}


def reset_and_mark(phases: dict, run_phases: list[int]) -> dict:
    """Mirror start_run's order: pending reset, then stale marking."""
    for n in run_phases:
        phases[str(n)] = {"status": "pending"}
    _mark_stale_phases(phases, run_phases)
    return phases


def test_revision_leg_marks_downstream():  # S1
    phases = reset_and_mark(all_completed(), [2, 3, 4])
    assert phases["5"] == {"status": "completed", "stale": True}
    assert phases["6"] == {"status": "completed", "stale": True}
    for n in ("2", "3", "4"):
        assert phases[n] == {"status": "pending"}
    assert phases["1"] == {"status": "completed"}


def test_reexplore_marks_everything_downstream():  # S2
    phases = reset_and_mark(all_completed(), [1])
    for n in ("2", "3", "4", "5", "6"):
        assert phases[n].get("stale") is True


def test_approve_leg_clears():  # S3
    phases = reset_and_mark(all_completed(), [2, 3, 4])
    reset_and_mark(phases, [5, 6])
    assert phases["5"] == {"status": "pending"}
    assert phases["6"] == {"status": "pending"}


def test_only_completed_marked():  # S4
    phases = {
        "5": {"status": "error"},
        "6": {"status": "canceled"},
        "3": {"status": "pending"},
    }
    _mark_stale_phases(phases, [2])
    assert "stale" not in phases["5"]
    assert "stale" not in phases["6"]
    assert "stale" not in phases["3"]


def test_phase_run_pops_stale(tmp_path: Path):  # S5
    state_dir = tmp_path / ".instantdemo"
    state_dir.mkdir()
    state_mod.save(state_dir, {
        "phases": {"6": {"status": "completed", "stale": True}}
    })
    with state_mod.phase_run(state_dir, 6):
        mid = state_mod.load(state_dir)["phases"]["6"]
        assert mid["status"] == "in_progress"
        assert "stale" not in mid
    final = state_mod.load(state_dir)["phases"]["6"]
    assert final["status"] == "completed"
    assert "stale" not in final
