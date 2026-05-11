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
    # Phase 3 (Gather/Inspect) needs to look at the live app's DOM to
    # write accurate selectors — Bash for `curl`/probe scripts and the
    # same browser tooling Phase 5 has. Without these the agent can
    # only guess from codebase reading. See issue #28.
    "phase3": frozenset({"Read", "Glob", "Grep", "Bash", "WebFetch"}),
    "phase4": frozenset({"Write"}),
    "phase5": frozenset({"Read", "Bash"}),
}


def session_id_for_phase(phase_number: int) -> str:
    """Map a 1-based phase number to its conversation session id /
    dispatcher key. The same string is used as `session_id=` on
    `client.query()` and as the lookup into PHASE_TOOLS."""
    return f"phase{phase_number}"


class PhaseDispatcher:
    """Tracks the active phase and serves a PreToolUse hook callback.

    The orchestrator sets `dispatcher.current_phase = "phaseN"` before
    issuing the query for phase N, and resets it after the query
    completes. The hook reads `current_phase` to decide whether the
    requested tool is allowed for that phase.

    Sequential-execution-only: do not run two phases concurrently
    against the same dispatcher.
    """

    def __init__(self) -> None:
        self.current_phase: str = ""

    async def hook(
        self,
        input_data: dict[str, Any],
        _tool_use_id: str | None,
        _ctx: Any,
    ) -> dict[str, Any]:
        phase = self.current_phase
        tool_name = input_data.get("tool_name", "")
        allowed = PHASE_TOOLS.get(phase, frozenset())
        if tool_name in allowed:
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


def make_agent_client(cwd: str) -> tuple[ClaudeSDKClient, PhaseDispatcher]:
    """Construct (but do not connect) a ClaudeSDKClient + PhaseDispatcher.

    Caller is responsible for `await client.connect()` and
    `await client.disconnect()`. Pass the same dispatcher to
    `run_query_on_client` so it can set `current_phase` before queries.
    """
    dispatcher = PhaseDispatcher()
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
