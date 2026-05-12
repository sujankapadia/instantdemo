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

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..intent import Intent

if TYPE_CHECKING:
    from claude_agent_sdk import (
        ClaudeAgentOptions,
        ClaudeSDKClient,
        ResultMessage,
    )

from .. import metrics as _metrics
from .. import state

PHASES = ("analyze", "narrate", "gather", "script", "validate")
"""Phase names in execution order, indexed by 1-based phase number."""

PHASE_NUMBERS = {name: i + 1 for i, name in enumerate(PHASES)}


@dataclass
class Context:
    """Inputs and resolved paths shared across phases.

    Built once by the CLI and passed to each phase's `run()` function.
    """

    url: str
    # Codebase root the agent reads from for Phase 1 / Phase 3.
    source: Path
    # Demo project directory — where state_dir, demo-script.json, and
    # demo.mp4 live. May differ from `source` when the demo project is
    # decoupled from the codebase (typical for the GUI). The CLI passes
    # `project == source` since its convention is to colocate them.
    project: Path
    describe: str | None        # optional — like the skill's $ARGUMENTS
    state_dir: Path             # project / ".instantdemo"
    output: Path                # final MP4 path (used by phase 5)
    tts: str                    # TTS provider name (used by phase 5)
    no_edit: bool               # if True, skip $EDITOR checkpoints
    # Structured intent for Phase 1 / Phase 2 — see issue #39.
    # Defaults to an empty Intent so callers that don't yet pass one
    # (e.g. older tests) keep working. CLI synthesizes from
    # `describe`; GUI loads from intent.json or builds from form
    # values. Phases 3/4/5 don't read intent.
    intent: Intent = field(default_factory=Intent)

    # Long-lived ClaudeSDKClient injected by the CLI for the duration of
    # a generate/phase command. Phases call client.query() against this.
    # Typed as Any to avoid forcing every importer of phases to also
    # import the SDK; the real type is claude_agent_sdk.ClaudeSDKClient.
    client: Any | None = None

    # The PhaseDispatcher paired with `client`. Phases must set
    # dispatcher.current_phase before invoking the SDK so the PreToolUse
    # hook routes per-phase tool allowlists correctly. run_query_on_client
    # handles the set/reset for callers.
    dispatcher: Any | None = None

    # Optional callback for emitting structured events (text chunks,
    # tool use, phase boundaries). The CLI leaves this None — phases
    # only print to stdout. The GUI server sets it to a queue-pusher
    # so the SSE endpoint can stream events to the browser. Signature:
    # `(event: dict[str, Any]) -> None`.
    event_emitter: Any | None = None

    @property
    def script_path(self) -> Path:
        """Path to the user-facing demo-script.json (Phase 4 output).

        Always resolves from `project`, never `source`. Pre-#30 this
        used `source` and was fine because CLI ran with
        `source == project`. After the GUI's #27 added a separate
        source field, the script would have spilled into the user's
        codebase. See issue #30."""
        return self.project / "demo-script.json"

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


async def run_query(prompt: str, options: "ClaudeAgentOptions") -> tuple[str, Any]:
    """Run a one-shot `query()` against the Agent SDK and stream agent
    text to stdout.

    Retained for the rare case where a fully isolated subprocess run is
    wanted (mostly tests). The phase pipeline uses run_query_on_client
    instead, which reuses one ClaudeSDKClient across all phases.
    """
    from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, query

    text_chunks: list[str] = []
    result = None
    async for msg in query(prompt=prompt, options=options):
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    print(block.text, flush=True)
                    text_chunks.append(block.text)
        elif isinstance(msg, ResultMessage):
            result = msg
    return "\n".join(text_chunks), result


async def run_query_on_client(
    context: "Context",
    prompt: str,
    session_id: str,
) -> tuple[str, Any]:
    """Run a prompt against the Context's connected ClaudeSDKClient.

    Sets `context.dispatcher.current_phase = session_id` so the
    PreToolUse hook dispatches tool permissions to the right phase
    allowlist, then resets it after the response completes.

    Returns (collected_text, result_message). result_message is the
    final ResultMessage; the loop breaks on it so the iterator doesn't
    block waiting for further messages on this turn.
    """
    from claude_agent_sdk import (
        AssistantMessage,
        ResultMessage,
        StreamEvent,
        TextBlock,
    )

    if context.client is None or context.dispatcher is None:
        raise RuntimeError(
            "run_query_on_client requires both context.client and "
            "context.dispatcher to be set. The CLI's "
            "_run_phases_with_client should provide both."
        )

    context.dispatcher.current_phase = session_id
    emit = context.event_emitter
    try:
        text_chunks: list[str] = []
        result = None
        # Whether any token deltas streamed during the current turn.
        # We use this to decide whether AssistantMessage's TextBlocks
        # need a fallback emit — if the agent returned text without
        # streaming (typical for some error paths or non-streaming
        # responses), the deltas never fired and the drawer would
        # otherwise stay empty.
        streamed_any_text = False
        await context.client.query(prompt, session_id=session_id)
        async for msg in context.client.receive_response():
            if isinstance(msg, StreamEvent):
                # Per-token text deltas. include_partial_messages=True on
                # ClaudeAgentOptions is what makes these arrive (otherwise
                # we'd only see the AssistantMessage at end of turn).
                evt = msg.event or {}
                if evt.get("type") == "content_block_delta":
                    delta = evt.get("delta") or {}
                    if delta.get("type") == "text_delta":
                        token = delta.get("text") or ""
                        if token:
                            streamed_any_text = True
                            print(token, end="", flush=True)
                            if emit is not None:
                                emit(
                                    {
                                        "type": "text_chunk",
                                        "session_id": session_id,
                                        "text": token,
                                    }
                                )
            elif isinstance(msg, AssistantMessage):
                # End-of-turn message. We collect the canonical text for
                # the return value, emit tool-use events (tools come at
                # the message level, not stream level), and — if no
                # deltas streamed for this turn — fall back to printing
                # / emitting the TextBlock text directly so the user
                # sees something.
                printed_newline = False
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        text_chunks.append(block.text)
                        if not streamed_any_text:
                            # No deltas fired — print + emit fallback
                            # so CLI stdout and the GUI drawer aren't
                            # silently empty (e.g., on a billing error
                            # the API returns text without streaming).
                            print(block.text, flush=True)
                            printed_newline = True
                            if emit is not None:
                                emit(
                                    {
                                        "type": "text_chunk",
                                        "session_id": session_id,
                                        "text": block.text,
                                    }
                                )
                        elif not printed_newline:
                            print(flush=True)
                            printed_newline = True
                    elif type(block).__name__ == "ToolUseBlock":
                        if emit is not None:
                            emit(
                                {
                                    "type": "tool_use",
                                    "session_id": session_id,
                                    "tool": getattr(block, "name", ""),
                                    "tool_input": getattr(block, "input", {}),
                                }
                            )

                # Detect agent-side errors surfaced by the SDK on the
                # AssistantMessage (billing_error, rate_limit, etc.).
                # Any text content has already been emitted above, so
                # the user sees the explanation; raising here marks
                # the phase as errored rather than silently continuing
                # with garbage content as a "successful" artifact.
                msg_error = getattr(msg, "error", None)
                if msg_error:
                    detail = "\n".join(text_chunks).strip() or "(no message)"
                    raise RuntimeError(f"Agent error ({msg_error}): {detail}")

                # Reset for the next turn (multi-turn runs interleave
                # tool use → tool result → another agent turn).
                streamed_any_text = False
            elif isinstance(msg, ResultMessage):
                if msg.is_error:
                    detail = (
                        getattr(msg, "result", None)
                        or "\n".join(text_chunks).strip()
                        or "(no message)"
                    )
                    subtype = getattr(msg, "subtype", "unknown")
                    raise RuntimeError(
                        f"Agent run errored (subtype={subtype}): {detail}"
                    )
                result = msg
                break
        return "\n".join(text_chunks), result
    finally:
        context.dispatcher.current_phase = ""


def record_phase_result(
    context: "Context", phase_number: int, result: "ResultMessage"
) -> None:
    """Capture metrics from a query() ResultMessage.

    Writes to two places:
      - state.json (current state — overwrites prior phase entry on re-run)
      - metrics.jsonl (append-only history — one row per phase per run)

    `cost_usd` is recorded as the DELTA for this run, not the cumulative
    total. The SDK's `ResultMessage.total_cost_usd` is cumulative for
    the session_id within the long-lived client, so re-running the
    same phase would otherwise inflate the recorded cost. We subtract
    the previously-seen total (tracked per session_id in the
    dispatcher) to get the per-run cost. See issue #45.
    """
    state_dir = context.state_dir
    dispatcher = context.dispatcher
    current_total = result.total_cost_usd or 0.0
    session_id = result.session_id or ""
    if dispatcher is not None and session_id:
        prev_total = dispatcher.session_cost_totals.get(session_id, 0.0)
        delta = max(0.0, current_total - prev_total)
        dispatcher.session_cost_totals[session_id] = current_total
    else:
        # No dispatcher available (CLI in some edge cases or tests) —
        # fall back to the SDK total. Loses delta semantics but doesn't
        # crash; resulting cost may be inflated on re-runs.
        delta = current_total

    usage = result.usage or {}
    fields = {
        "cost_usd": delta,
        "duration_ms": result.duration_ms,
        "duration_api_ms": result.duration_api_ms,
        "num_turns": result.num_turns,
        "is_error": result.is_error,
        "stop_reason": result.stop_reason,
        "session_id_phase": result.session_id,
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "cache_creation_tokens": usage.get("cache_creation_input_tokens"),
        "cache_read_tokens": usage.get("cache_read_input_tokens"),
    }

    # state.json — phase entry gets these fields merged in
    state.record_phase_metrics(state_dir, phase_number, **fields)

    # metrics.jsonl — one append-only row, with run identifiers added
    snapshot = state.load(state_dir)
    _metrics.append(
        state_dir,
        run_session_id=snapshot.get("session_id"),
        phase_number=phase_number,
        phase_name=phase_name_from_number(phase_number),
        **fields,
    )


def summarize_run(phase_number: int, artifact: Path, result: "ResultMessage") -> str:
    """Format the per-phase one-liner shown after a successful run."""
    return (
        f"\nPhase {phase_number} done — {artifact} "
        f"(${result.total_cost_usd:.2f}, {result.duration_ms / 1000:.1f}s, "
        f"{result.num_turns} turns)"
    )
