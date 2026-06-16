"""Unit tests for the agent backend's tools + jail + allowlist (M9).
Spec: tests/test-specs/test_agent_backend.md."""

from __future__ import annotations

import asyncio
from pathlib import Path

from instantdemo.agent_backend import (
    JailToolset,
    make_tools,
    phase_allows,
    tool_glob,
    tool_grep,
    tool_read,
)
from instantdemo.agent_client import _jail_violation


# ── tool bodies ──────────────────────────────────────────────────────
def test_read_numbers_lines(tmp_path: Path):  # AB1
    f = tmp_path / "a.txt"
    f.write_text("foo\nbar\nbaz")
    assert tool_read(str(f)) == "1\tfoo\n2\tbar\n3\tbaz"
    # offset + limit window
    assert tool_read(str(f), offset=1, limit=1) == "2\tbar"


def test_glob_lists_matching_files(tmp_path: Path):  # AB2
    (tmp_path / "x.py").write_text("")
    (tmp_path / "y.py").write_text("")
    (tmp_path / "z.txt").write_text("")
    (tmp_path / "sub").mkdir()
    out = tool_glob("*.py", cwd=tmp_path).splitlines()
    assert sorted(Path(p).name for p in out) == ["x.py", "y.py"]


def test_grep_returns_file_line_text(tmp_path: Path):  # AB3
    f = tmp_path / "src.py"
    f.write_text("import os\nx = data_testid\nimport sys")
    out = tool_grep("data_testid", path=str(f))
    assert out == f"{f}:2: x = data_testid"


# ── jail + allowlist ─────────────────────────────────────────────────
def test_phase_allows_mirrors_phase_tools():  # AB4
    assert phase_allows("phase1", "Bash")
    assert phase_allows("phase1", "Grep")
    assert phase_allows("phase3", "Read")
    assert not phase_allows("phase3", "Bash")   # phase 3 reads source only
    assert not phase_allows("phase2", "Read")   # phase 2 has no tools
    assert not phase_allows("phase5", "Bash")   # unknown/deterministic → deny
    assert not phase_allows("nope", "Read")


def test_jail_rule_blocks_outside_roots(tmp_path: Path):  # AB5
    root = tmp_path / "project"
    root.mkdir()
    roots = [root]
    # Inside the jail → allowed (None).
    inside = root / "note.txt"
    assert _jail_violation("Read", {"file_path": str(inside)}, roots, root) is None
    # Outside the jail → violation (returns the offending path).
    outside = tmp_path / "secret.txt"
    assert _jail_violation("Read", {"file_path": str(outside)}, roots, root) is not None
    # Bash carries no path field → never a path violation.
    assert _jail_violation("Bash", {"command": "ls /etc"}, roots, root) is None


def test_jail_denial_informs_not_raises(tmp_path: Path):  # AB6
    root = tmp_path / "project"
    root.mkdir()
    jail = JailToolset(make_tools(root), [root], root)
    outside = tmp_path / "secret.txt"
    # ctx/tool are unused on the denial path (it returns before super()).
    result = asyncio.run(
        jail.call_tool("Read", {"file_path": str(outside)}, None, None)
    )
    assert isinstance(result, str)
    assert "Blocked by the sandbox" in result
