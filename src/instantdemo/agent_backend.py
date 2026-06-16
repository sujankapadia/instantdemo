"""Agent backend (M9) — the seam between the pipeline's per-phase agent
loop and the underlying runtime.

The pipeline historically ran on the Claude Agent SDK (long-lived
`ClaudeSDKClient` + `PhaseDispatcher` PreToolUse hook + per-phase tool
allowlists). This module is the start of porting that loop onto Pydantic
AI so per-phase model choice becomes possible (see
`AGENT_SDK_PORTABILITY.md`).

This first slice provides the Pydantic-AI-side equivalents of the SDK's
built-in tools and its filesystem jail / tool allowlist — the pieces the
SDK shipped for free:

- four tools (`Bash`, `Read`, `Glob`, `Grep`) as a `FunctionToolset`,
  named to match the SDK's `PHASE_TOOLS` allowlist;
- a `JailToolset` that reuses `agent_client._jail_violation` verbatim
  (the same path-resolution + allowed-roots check), the analog of the
  PreToolUse hook;
- a `FilteredToolset` per phase that exposes only that phase's allowed
  tools.

The agent loop, structured output, and result normalization land in
later commits; the tools/jail/allowlist are built and tested first
because they need no model.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from pydantic_ai import (
    FilteredToolset,
    FunctionToolset,
    ModelRetry,
    RunContext,
    WrapperToolset,
)

# Reuse the SDK-era jail + allowlist verbatim — same path rules, same
# per-phase tool sets. Do NOT re-derive (they encode tested behavior).
from .agent_client import PHASE_TOOLS, _jail_violation

_BASH_TIMEOUT_S = 120
_OUTPUT_CAP = 8000
_READ_DEFAULT_LIMIT = 2000
_MATCH_CAP = 200


# ── tool bodies (plain functions — unit-testable without a model) ─────
def tool_bash(command: str, cwd: Path) -> str:
    """Run a shell command in the working directory; combined
    stdout+stderr, tail-capped. (Bash is unjailed, as in the SDK era —
    shell jailing needs OS sandboxing, not a path check.)"""
    proc = subprocess.run(
        command, shell=True, cwd=str(cwd),
        capture_output=True, text=True, timeout=_BASH_TIMEOUT_S,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return out[-_OUTPUT_CAP:] if len(out) > _OUTPUT_CAP else out


def tool_read(file_path: str, offset: int = 0, limit: int = _READ_DEFAULT_LIMIT) -> str:
    """Read a text file as numbered lines (1-based), from `offset`
    (0-based) for up to `limit` lines — mirrors the SDK Read shape."""
    lines = Path(file_path).read_text(errors="replace").splitlines()
    chunk = lines[offset: offset + limit]
    return "\n".join(f"{offset + i + 1}\t{ln}" for i, ln in enumerate(chunk))


def tool_glob(pattern: str, path: str = "", cwd: Path | None = None) -> str:
    """List files matching a glob `pattern` under `path` (or cwd)."""
    base = Path(path) if path else (cwd or Path.cwd())
    matches = sorted(str(p) for p in base.glob(pattern) if p.is_file())
    return "\n".join(matches[:_MATCH_CAP]) or "(no matches)"


def tool_grep(
    pattern: str, path: str = "", glob: str = "*", cwd: Path | None = None
) -> str:
    """Regex-search files for `pattern`. Returns `file:line: text`."""
    base = Path(path) if path else (cwd or Path.cwd())
    rx = re.compile(pattern)
    out: list[str] = []
    files = [base] if base.is_file() else base.rglob(glob)
    for f in files:
        if not f.is_file():
            continue
        try:
            text = f.read_text(errors="replace")
        except OSError:
            continue
        for i, ln in enumerate(text.splitlines(), 1):
            if rx.search(ln):
                out.append(f"{f}:{i}: {ln.strip()[:200]}")
                if len(out) >= _MATCH_CAP:
                    return "\n".join(out)
    return "\n".join(out) or "(no matches)"


def make_tools(cwd: Path) -> FunctionToolset:
    """The four tools as a FunctionToolset, named to match PHASE_TOOLS."""
    ts = FunctionToolset()

    @ts.tool(name="Bash")
    def _bash(ctx: RunContext, command: str) -> str:  # noqa: ARG001
        """Run a shell command in the sandbox working directory."""
        return tool_bash(command, cwd)

    @ts.tool(name="Read")
    def _read(ctx: RunContext, file_path: str, offset: int = 0,  # noqa: ARG001
              limit: int = _READ_DEFAULT_LIMIT) -> str:
        """Read a file as numbered lines."""
        return tool_read(file_path, offset, limit)

    @ts.tool(name="Glob")
    def _glob(ctx: RunContext, pattern: str, path: str = "") -> str:  # noqa: ARG001
        """List files matching a glob pattern."""
        return tool_glob(pattern, path, cwd)

    @ts.tool(name="Grep")
    def _grep(ctx: RunContext, pattern: str, path: str = "",  # noqa: ARG001
              glob: str = "*") -> str:
        """Regex-search files; returns file:line: text."""
        return tool_grep(pattern, path, glob, cwd)

    return ts


# ── jail (the PreToolUse-hook analog) ─────────────────────────────────
class JailToolset(WrapperToolset):
    """Intercept every tool call before execution and deny any whose
    path argument escapes `allowed_roots` — reusing the SDK-era
    `_jail_violation` so the rules are identical. Bash is unjailed."""

    def __init__(self, wrapped, allowed_roots: list[Path], cwd: Path):
        super().__init__(wrapped)
        self._roots = [Path(r) for r in allowed_roots]
        self._cwd = Path(cwd)

    async def call_tool(self, name, tool_args, ctx, tool):
        violation = _jail_violation(name, tool_args or {}, self._roots, self._cwd)
        if violation is not None:
            raise ModelRetry(
                f"Blocked by the sandbox: {violation} is outside the "
                "allowed directories. Stay within the project."
            )
        return await super().call_tool(name, tool_args, ctx, tool)


def phase_allows(phase_key: str, tool_name: str) -> bool:
    """Does `phase_key` (e.g. 'phase3') permit `tool_name`? Mirrors the
    SDK dispatcher's PHASE_TOOLS lookup (default-deny)."""
    return tool_name in PHASE_TOOLS.get(phase_key, frozenset())


def build_phase_toolset(phase_key: str, allowed_roots: list[Path], cwd: Path):
    """The jailed, per-phase-filtered toolset for `phase_key`: only that
    phase's allowed tools are exposed, and file tools are jailed."""
    jailed = JailToolset(make_tools(Path(cwd)), allowed_roots, cwd)
    return FilteredToolset(
        jailed, lambda ctx, td: phase_allows(phase_key, td.name)
    )
