"""Long-lived ClaudeSDKClient with a per-phase PreToolUse hook dispatcher.

Replaces the prior pattern of one `query()` call per phase. The cold-start
cost (subprocess launch, auth, session init — ~5-10s each) is paid once
at connect() instead of 5 times across a cold-start workflow.

Per-phase tool allowlists are preserved exactly. The mechanism uses a
`PreToolUse` hook (rather than the SDK's `can_use_tool` callback —
`can_use_tool` only fires for tools the CLI would otherwise prompt the
user for, and with permission_mode=bypassPermissions or no allowed_tools
restriction the prompt path is skipped, so the callback never fires).
A `PreToolUse` hook fires before every tool call unconditionally and
returns an allow/deny decision, which is what we need.

The hook needs to know which phase is active. We can't read it from
the hook input (the SDK's `session_id` field is a SDK-internal UUID,
not the user-supplied phase name) and can't use ContextVar (the hook
runs in the SDK's internal task, where our async context isn't
propagated). The dispatcher therefore holds a mutable instance
attribute `current_phase` that the orchestrator sets before each
phase's queries. This is safe because phases run sequentially against
a single client.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    HookMatcher,
)


# Phase session_id (e.g. "phase1") → tools that phase is allowed to use.
# Mirrors the per-phase `allowed_tools` values from before the migration.
PHASE_TOOLS: dict[str, frozenset[str]] = {
    "phase1": frozenset({"Read", "Glob", "Grep"}),
    "phase2": frozenset(),
    "phase3": frozenset({"Read", "Glob", "Grep"}),
    # Phase 4 (Explore) probes the live app via Bash + Playwright,
    # reading Phase 3's hypothesis to verify selectors against reality.
    # No Write — the agent's response text is saved by the runner.
    "phase4": frozenset({"Read", "Bash"}),
    # Phase 5 (Build) is deterministic since M0 — no agent runs, so
    # it has no PHASE_TOOLS entry (the dispatcher default-denies any
    # stray phase5 tool call).
    "phase6": frozenset({"Read", "Bash"}),
}


# Tools whose inputs name filesystem paths, and the input fields that
# carry them. Used by the optional path jail (see PhaseDispatcher).
# Glob's `pattern` is included because an absolute pattern
# ("/Users/**/*.html") reaches outside the search `path` entirely.
_FILE_TOOL_PATH_FIELDS: dict[str, tuple[str, ...]] = {
    "Read": ("file_path",),
    "Write": ("file_path",),
    "Glob": ("path", "pattern"),
    "Grep": ("path",),
}


def _jail_violation(
    tool_name: str,
    tool_input: dict[str, Any],
    allowed_roots: list[Path],
    cwd: Path,
) -> str | None:
    """Return the offending path if `tool_input` reaches outside
    `allowed_roots`, else None.

    Relative paths resolve against `cwd` (matching the CLI's tool
    behavior); `~` is expanded; symlinks are resolved so a link
    inside the jail can't point out of it. A missing path field is
    fine — Glob/Grep default to cwd, which the caller guarantees is
    inside the jail. Glob patterns are only checked when absolute
    (a relative pattern stays under the jail-checked `path`/cwd).
    """
    for field in _FILE_TOOL_PATH_FIELDS.get(tool_name, ()):
        raw = tool_input.get(field)
        if not raw or not isinstance(raw, str):
            continue
        if field == "pattern" and not raw.startswith(("/", "~")):
            continue
        if field == "pattern":
            # Resolve only the fixed prefix before the first glob
            # metacharacter — "/Users/foo/**/*.html" jails on
            # "/Users/foo".
            for meta in ("*", "?", "["):
                idx = raw.find(meta)
                if idx != -1:
                    raw = raw[:idx]
                    break
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = cwd / candidate
        candidate = candidate.resolve()
        if not any(
            candidate == root or candidate.is_relative_to(root)
            for root in allowed_roots
        ):
            return str(candidate)
    return None


def session_id_for_phase(
    phase_number: int, run_id: str | None = None
) -> str:
    """Map a 1-based phase number to its conversation session id.

    When `run_id` is provided, the session id includes an 8-char
    prefix of it, e.g. `"phase4-abc12345"`. This makes each
    pipeline run get a fresh per-phase session — preventing the
    SDK from threading prior runs' conversation history into new
    queries. See issue #53.

    When `run_id` is None, returns the bare `"phaseN"` (legacy
    behavior, kept for callers without a run id).

    The PreToolUse hook strips the suffix to recover the
    `"phaseN"` key for PHASE_TOOLS lookup, so per-phase tool
    allowlists work uniformly across both forms.
    """
    base = f"phase{phase_number}"
    if run_id:
        return f"{base}-{run_id[:8]}"
    return base


class PhaseDispatcher:
    """Tracks the active phase and serves a PreToolUse hook callback.

    The orchestrator sets `dispatcher.current_phase = "phaseN"` before
    issuing the query for phase N, and resets it after the query
    completes. The hook reads `current_phase` to decide whether the
    requested tool is allowed for that phase.

    Sequential-execution-only: do not run two phases concurrently
    against the same dispatcher.
    """

    def __init__(
        self,
        allowed_roots: list[Path] | None = None,
        cwd: Path | None = None,
    ) -> None:
        self.current_phase: str = ""
        # Running totals per session_id. The SDK's
        # ResultMessage.total_cost_usd is cumulative for the session_id,
        # so we track the previous total here and let
        # record_phase_result compute the per-run delta. Resets when
        # the dispatcher is recreated (i.e. when the SDK client is
        # rebuilt for a new server session). See issue #45.
        self.session_cost_totals: dict[str, float] = {}
        # Optional filesystem jail. When set, Read/Write/Glob/Grep
        # calls whose paths resolve outside these roots are denied —
        # the per-phase allowlist controls WHICH tools a phase gets,
        # this controls WHERE those tools may reach. Needed because
        # the agent will otherwise locate the app's source anywhere
        # on disk (observed: a source-free Phase 3 run found the real
        # repo via Glob and read it). Bash (phases 4/6) is NOT
        # covered — path-jailing arbitrary shell commands needs OS
        # sandboxing, out of scope here.
        self.allowed_roots = (
            [p.resolve() for p in allowed_roots] if allowed_roots else None
        )
        self.cwd = (cwd or Path.cwd()).resolve()

    async def hook(
        self,
        input_data: dict[str, Any],
        _tool_use_id: str | None,
        _ctx: Any,
    ) -> dict[str, Any]:
        phase = self.current_phase
        # current_phase may be a session id like "phase4-abc12345"
        # after #53. Strip any per-run suffix to recover the
        # PHASE_TOOLS key.
        phase_key = phase.split("-", 1)[0]
        tool_name = input_data.get("tool_name", "")
        allowed = PHASE_TOOLS.get(phase_key, frozenset())
        if tool_name in allowed:
            if self.allowed_roots is not None:
                violation = _jail_violation(
                    tool_name,
                    input_data.get("tool_input") or {},
                    self.allowed_roots,
                    self.cwd,
                )
                if violation is not None:
                    return {
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "permissionDecision": "deny",
                            "permissionDecisionReason": (
                                f"{tool_name} on {violation!r} is outside "
                                "the allowed project directories. This "
                                "run restricts file access to: "
                                f"{[str(r) for r in self.allowed_roots]}. "
                                "Work from the prior phase artifacts and "
                                "live-app observations instead."
                            ),
                        }
                    }
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "allow",
                }
            }
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    f"Tool {tool_name!r} not permitted in "
                    f"{phase or '(no phase set)'}; "
                    f"allowed: {sorted(allowed) or 'none'}"
                ),
            }
        }


def make_agent_client(
    cwd: str,
    allowed_roots: list[Path] | None = None,
) -> tuple[ClaudeSDKClient, PhaseDispatcher]:
    """Construct (but do not connect) a ClaudeSDKClient + PhaseDispatcher.

    Caller is responsible for `await client.connect()` and
    `await client.disconnect()`. Pass the same dispatcher to
    `run_query_on_client` so it can set `current_phase` before queries.

    `allowed_roots` enables the filesystem jail: file tools
    (Read/Write/Glob/Grep) are denied outside these roots. None
    (default) preserves the historical unrestricted behavior.
    """
    dispatcher = PhaseDispatcher(allowed_roots=allowed_roots, cwd=Path(cwd))
    # Cast hook list to the SDK's expected type — Pyright can't unify
    # our concrete return-dict type with the union HookJSONOutput.
    options = ClaudeAgentOptions(
        cwd=cwd,
        permission_mode="bypassPermissions",
        # Per-token streaming. Without this, the SDK only emits
        # AssistantMessage at end-of-turn (one big chunk). With it, we
        # also get StreamEvent messages carrying content_block_delta
        # text deltas — that's what makes the agent log feel "live"
        # in the GUI drawer.
        include_partial_messages=True,
        hooks={
            "PreToolUse": [HookMatcher(matcher=None, hooks=[dispatcher.hook])],  # type: ignore[list-item]
        },
    )
    client = ClaudeSDKClient(options=options)
    return client, dispatcher
