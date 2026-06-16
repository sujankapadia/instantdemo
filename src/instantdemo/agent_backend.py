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
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic_ai import (
    Agent,
    CachePoint,
    FilteredToolset,
    FunctionToolCallEvent,
    FunctionToolset,
    ModelRetry,
    PartDeltaEvent,
    RunContext,
    TextPartDelta,
    UsageLimits,
    WrapperToolset,
)

# Pydantic AI defaults to request_limit=50 per agent.run(); the SDK had
# no such cap. Tool-heavy phases (1/3/4 read source + drive Playwright
# over many calls) exceed 50 in one run — raise to a generous backstop
# that still catches a runaway loop.
_REQUEST_LIMIT = 300

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


def _resolve(path: str, cwd: Path) -> Path:
    """Resolve a (possibly relative) tool path against the agent's working
    directory — the SDK ran tools with cwd set, and the jail checks
    containment against the same cwd, so the bodies must match."""
    p = Path(path)
    return p if p.is_absolute() else cwd / p


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
        return tool_read(str(_resolve(file_path, cwd)), offset, limit)

    @ts.tool(name="Glob")
    def _glob(ctx: RunContext, pattern: str, path: str = "") -> str:  # noqa: ARG001
        """List files matching a glob pattern."""
        return tool_glob(pattern, str(_resolve(path, cwd)) if path else "", cwd)

    @ts.tool(name="Grep")
    def _grep(ctx: RunContext, pattern: str, path: str = "",  # noqa: ARG001
              glob: str = "*") -> str:
        """Regex-search files; returns file:line: text."""
        return tool_grep(pattern, str(_resolve(path, cwd)) if path else "", glob, cwd)

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


# ── model routing ─────────────────────────────────────────────────────
def resolve_model(spec: str):
    """`anthropic:claude-...` (or any provider:model) passes through as a
    native pydantic-ai model string; `openrouter:<id>` routes through
    OpenRouter's OpenAI-compatible endpoint (one key, many models)."""
    if spec.startswith("openrouter:"):
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openrouter import OpenRouterProvider

        return OpenAIChatModel(
            spec.split(":", 1)[1], provider=OpenRouterProvider()
        )
    return spec


def _cost_usd(spec: str, usage) -> float:
    """Best-effort per-call cost from token usage via genai-prices.
    Returns 0.0 if the price lookup fails (cost is non-fatal telemetry)."""
    import genai_prices

    provider, _, model_ref = spec.partition(":")
    provider_id = "openrouter" if provider == "openrouter" else provider
    if provider == "openrouter":
        model_ref = spec.split(":", 1)[1]
    gusage = genai_prices.Usage(
        input_tokens=usage.input_tokens or 0,
        output_tokens=usage.output_tokens or 0,
        cache_read_tokens=getattr(usage, "cache_read_tokens", 0) or 0,
        cache_write_tokens=getattr(usage, "cache_write_tokens", 0) or 0,
    )
    try:
        calc = genai_prices.calc_price(
            gusage, model_ref=model_ref, provider_id=provider_id
        )
        return float(getattr(calc, "total_price", 0.0) or 0.0)
    except Exception:  # noqa: BLE001 — pricing is best-effort telemetry
        return 0.0


# ── normalized result (the fields record_phase_result reads) ──────────
@dataclass
class AgentResult:
    output: Any           # the typed Pydantic object, or str for text runs
    session_id: str
    usage: dict           # SDK-shaped: input/output/cache_* token counts
    total_cost_usd: float = 0.0
    num_turns: int = 1
    duration_ms: int | None = None
    duration_api_ms: int | None = None
    is_error: bool = False
    stop_reason: str | None = "end_turn"


# ── the Pydantic AI backend ───────────────────────────────────────────
class PydanticAIBackend:
    """Runs a phase's agent on Pydantic AI with a per-phase model. Keeps
    a `session_id -> message_history` store so multi-call phases (2/3)
    accumulate context as the SDK sessions did; a `CachePoint` on each
    turn preserves the M7 "paid once" prompt-caching economics (verified
    by scripts/explore/cache_probe.py)."""

    def __init__(
        self,
        *,
        default_model: str = "anthropic:claude-sonnet-4-6",
        models: dict[str, str] | None = None,
        allowed_roots: list[Path] | None = None,
        cwd: Path | None = None,
    ):
        self.default_model = default_model
        self.models = models or {}          # phase_key -> model spec
        self.allowed_roots = [Path(r) for r in (allowed_roots or [])]
        self.cwd = Path(cwd or Path.cwd())
        self._sessions: dict[str, list] = {}

    def _spec_for(self, phase_key: str) -> str:
        return self.models.get(phase_key, self.default_model)

    async def run_structured(
        self, context, prompt: str, session_id: str, *,
        output_type, validate=None, phase_number: int = 0,
    ) -> AgentResult:
        """Run a structured-output call. `validate` is the existing
        dict->problems validator; it's wrapped as an output_validator
        that raises ModelRetry (native retry replaces the manual one)."""
        def _ov(ctx, output):  # noqa: ARG001
            if validate is not None:
                payload = output.model_dump() if hasattr(output, "model_dump") else output
                problems = validate(payload)
                if problems:
                    raise ModelRetry(
                        "Your output failed validation:\n"
                        + "\n".join(f"- {p}" for p in problems)
                        + "\nRe-emit the corrected output."
                    )
            return output

        return await self._run(
            context, prompt, session_id,
            output_type=output_type, output_validator=_ov,
        )

    async def run_text(self, context, prompt: str, session_id: str) -> AgentResult:
        """Run a plain-text call (phases 4/6: findings/directive parsed
        from prose by the runner)."""
        return await self._run(
            context, prompt, session_id, output_type=str, output_validator=None,
        )

    async def _run(
        self, context, prompt: str, session_id: str, *,
        output_type, output_validator,
    ) -> AgentResult:
        phase_key = session_id.split("-", 1)[0]
        spec = self._spec_for(phase_key)
        toolsets = []
        if PHASE_TOOLS.get(phase_key):
            toolsets = [build_phase_toolset(phase_key, self.allowed_roots, self.cwd)]
        agent = Agent(
            resolve_model(spec), output_type=output_type, retries=2,
            toolsets=toolsets,
        )
        if output_validator is not None:
            agent.output_validator(output_validator)

        emit = getattr(context, "event_emitter", None)

        # SSE parity. NOTE: structured (output_type) runs use tool-mode
        # output, so they emit NO text deltas — `text_chunk` fires only on
        # text runs (phases 4/6). `tool_use` fires for real tool calls;
        # the runner-emitted progress events (chapter/scene/render, M7/M8)
        # carry the rest of the GUI's progress UX.
        async def handler(ctx, stream):  # noqa: ARG001
            async for ev in stream:
                if isinstance(ev, PartDeltaEvent) and isinstance(ev.delta, TextPartDelta):
                    tok = ev.delta.content_delta
                    if tok and emit is not None:
                        emit({"type": "text_chunk", "session_id": session_id, "text": tok})
                elif isinstance(ev, FunctionToolCallEvent) and emit is not None:
                    p = ev.part
                    emit({
                        "type": "tool_use", "session_id": session_id,
                        "tool": getattr(p, "tool_name", ""),
                        "tool_input": getattr(p, "args", {}),
                    })

        history = self._sessions.get(session_id)
        t0 = time.monotonic()
        result = await agent.run(
            [prompt, CachePoint()],           # CachePoint → prefix paid once
            message_history=history,
            event_stream_handler=handler,
            usage_limits=UsageLimits(request_limit=_REQUEST_LIMIT),
        )
        dur_ms = int((time.monotonic() - t0) * 1000)
        self._sessions[session_id] = result.all_messages()

        u = result.usage
        return AgentResult(
            output=result.output,
            session_id=session_id,
            usage={
                "input_tokens": u.input_tokens,
                "output_tokens": u.output_tokens,
                "cache_creation_input_tokens": getattr(u, "cache_write_tokens", None),
                "cache_read_input_tokens": getattr(u, "cache_read_tokens", None),
            },
            total_cost_usd=_cost_usd(spec, u),
            num_turns=getattr(u, "requests", 1) or 1,
            duration_ms=dur_ms,
        )
