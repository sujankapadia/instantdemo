"""Phase runners for the InstantDemo workflow.

The six phases (GUI-facing names in parentheses):

    1. analyze   (Understand) — Read source, understand the product
    2. narrate   (Plan)       — Write the narrative
    3. gather    (Inspect)    — Source-based selector hypothesis
    4. explore   (Explore)    — Probe live app to verify selectors
    5. script    (Build)      — Emit demo-script.json
    6. render    (Render)     — Drift check + invoke the renderer

Each phase is implemented as a module with a `run(context)` function that
reads any prior-phase artifacts from the state directory, does its work,
and writes a single artifact back to the state directory. Phase 5 writes
the user-facing demo-script.json instead of a state-dir artifact, and
Phase 6 invokes the renderer (with a thin drift-check report alongside).
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

PHASES = ("analyze", "narrate", "gather", "explore", "script", "render")
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
    # TTS provider OVERRIDE for phase 6's renderer. None (the normal
    # case since M3) means "resolve from <project>/tts.json" —
    # pocket-tts/alba when no config exists. A string forces that
    # provider over the config (CLI --tts).
    tts: str | None
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

    # Per-pipeline-run identifier. When set, each phase derives its
    # session id as f"phase{N}-{run_id[:8]}" so the SDK doesn't
    # thread prior runs' conversation history into new queries. See
    # issue #53. Optional for callers (older tests, CLI before
    # threading) — None falls back to the legacy bare "phaseN" form.
    run_id: str | None = None

    # Scoped chapter revision (M5b): when section_scope names a
    # chapter, phases 2-4 operate ONLY on that chapter's scenes
    # (phase 2 re-plans them in place; 3 enriches them; 4 replays
    # the prefix as setup and verifies them) and phase 6 records
    # just that span and splices it into the existing film.
    # section_instruction carries the user's revision ask verbatim.
    section_scope: str | None = None
    section_instruction: str | None = None

    # M9 port: an optional Pydantic AI backend. When a phase number is in
    # `pydantic_phases`, the two query functions delegate to this backend
    # instead of the Claude Agent SDK. Empty by default → every phase
    # keeps the SDK path (behavior-preserving until a phase is enabled).
    backend: Any | None = None
    pydantic_phases: frozenset[int] = field(default_factory=frozenset)

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
        """Resolve the per-phase artifact path within the state dir.

        Phase 5 (Build) outputs demo-script.json in the project root —
        every other phase writes a markdown report in the state dir.
        """
        if phase_number == 5:
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


def get_phase_runner(number: int):
    """Lazy-import the phase module for `number` and return its async
    `run(context)` function. Single source of truth — both the CLI
    (`cli.py`) and the GUI (`server/routes/runs.py`) dispatch through
    here so adding a phase touches one place.

    The lazy import keeps the server's startup path light and avoids
    pulling in optional dependencies (e.g. Playwright for render)
    until they're actually needed.
    """
    name = phase_name_from_number(number)
    if name == "analyze":
        from . import analyze
        return analyze.run
    if name == "narrate":
        from . import narrate
        return narrate.run
    if name == "gather":
        from . import gather
        return gather.run
    if name == "explore":
        from . import explore
        return explore.run
    if name == "script":
        from . import script
        return script.run
    if name == "render":
        from . import render
        return render.run
    raise AssertionError(f"unreachable: phase {name}")  # pragma: no cover


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


def _phase_num(session_id: str) -> int:
    """Extract the phase number from a session id ('phase4-abc' -> 4)."""
    head = session_id.split("-", 1)[0]
    try:
        return int(head.removeprefix("phase"))
    except ValueError:
        return 0


def _use_backend(context: "Context", phase_number: int) -> bool:
    return (
        context.backend is not None
        and phase_number in context.pydantic_phases
    )


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
    # M9: text-output phases (4/6) delegate to the Pydantic AI backend
    # when enabled. Structured phases never reach here — run_structured_query
    # handles them via backend.run_structured before calling this.
    if _use_backend(context, _phase_num(session_id)):
        result = await context.backend.run_text(context, prompt, session_id)
        return result.output, result

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


async def run_structured_query(
    context: "Context",
    prompt: str,
    session_id: str,
    *,
    validate,
    phase_number: int,
    output_type=None,
) -> tuple[dict, Any]:
    """Run a prompt that must yield a fenced JSON payload; validate;
    retry once with the problems before failing.

    When this phase is ported (in `context.pydantic_phases`) and an
    `output_type` Pydantic model is supplied, delegates to the Pydantic
    AI backend: the model emits structured output (tool-mode, reliable),
    the same `validate` runs as an output_validator with native retry,
    and the typed result is returned to the caller as a dict — so the
    runner's downstream (dict-consuming) code is unchanged.

    The generalized #57 pattern: agents may reason in prose, but the
    response must end with one fenced ```json block. `validate` is a
    callable(payload) -> list[str] of problems (empty = valid). On
    failure (missing block or problems) a single corrective turn is
    issued in the same session — the agent still has full context, so
    "fix these problems" is cheap and usually sufficient.

    Returns (payload, last_result). The CALLER records phase metrics
    once with last_result: the SDK's total_cost_usd is cumulative per
    session, so a single record after the final turn captures the
    combined cost of both turns (recording per-turn would keep only
    the retry's delta — see record_phase_result).
    """
    # M9: structured phases (1/2/3) delegate to the Pydantic AI backend
    # when enabled. The typed output is converted back to a dict so the
    # runner's existing payload-consuming code needs no change.
    if _use_backend(context, phase_number) and output_type is not None:
        result = await context.backend.run_structured(
            context, prompt, session_id,
            output_type=output_type, validate=validate,
            phase_number=phase_number,
        )
        out = result.output
        # by_alias → fields like Phase 4's `from` (a Python keyword aliased
        # to `from_`) dump under their real JSON key. exclude_none → unset
        # optional fields are absent, not null, so the dict matches the SDK
        # fenced-JSON shape the runners expect (`"action" in updates` etc.).
        # No-op for phases 1/2/3 (no aliases; downstream uses .get()).
        payload = (
            out.model_dump(by_alias=True, exclude_none=True)
            if hasattr(out, "model_dump")
            else out
        )
        return payload, result

    from ..storyboard import extract_json_block

    def _problems_for(text: str) -> tuple[dict | None, list[str]]:
        payload = extract_json_block(text)
        if payload is None:
            return None, [
                "the response contained no parseable fenced ```json block"
            ]
        return payload, validate(payload)

    text, result = await run_query_on_client(
        context, prompt, session_id=session_id
    )
    if result is None:
        raise RuntimeError(
            f"Phase {phase_number}: the Claude Agent SDK did not return "
            "a ResultMessage."
        )
    payload, problems = _problems_for(text)
    if not problems:
        assert payload is not None
        return payload, result

    print(
        f"\n  Phase {phase_number} output failed validation "
        f"({len(problems)} problem(s)); asking the agent to correct it..."
    )
    fix_prompt = (
        "Your previous response failed validation:\n\n"
        + "\n".join(f"- {p}" for p in problems)
        + "\n\nRe-emit the COMPLETE corrected JSON payload (the entire "
        "object, not a diff), ending your response with the single "
        "fenced ```json block."
    )
    text, result = await run_query_on_client(
        context, fix_prompt, session_id=session_id
    )
    if result is None:
        raise RuntimeError(
            f"Phase {phase_number}: the Claude Agent SDK did not return "
            "a ResultMessage on the correction turn."
        )
    payload, problems = _problems_for(text)
    if problems:
        raise RuntimeError(
            f"Phase {phase_number} output still invalid after one "
            "correction attempt:\n"
            + "\n".join(f"  - {p}" for p in problems)
        )
    assert payload is not None
    return payload, result


def record_phase_result(
    context: "Context",
    phase_number: int,
    result: "ResultMessage",
    *,
    duration_ms: int | None = None,
    cost_usd_total: float | None = None,
    num_turns_total: int | None = None,
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

    `duration_ms` is the recorded **phase wall-clock**. When the caller
    passes None (the default), we fall back to the SDK's per-query
    measurement (`result.duration_ms`) — correct for phases whose only
    work is the agent query. For phases that do additional work after
    the agent returns (Phase 6 runs the renderer in an executor),
    callers MUST pass the measured phase wall-clock so this field
    reflects what the phase actually took. See issue #55.
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

    # Multi-call phases (M7: the chaptered phase 2 makes K+2 calls in
    # K+2 fresh sessions) pass their summed cost/turns; `result` is
    # the LAST call, whose own totals would undercount.
    if cost_usd_total is not None:
        delta = cost_usd_total

    usage = result.usage or {}
    fields = {
        "cost_usd": delta,
        "duration_ms": duration_ms if duration_ms is not None else result.duration_ms,
        "duration_api_ms": result.duration_api_ms,
        "num_turns": (
            num_turns_total if num_turns_total is not None else result.num_turns
        ),
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


def summarize_run(
    phase_number: int,
    artifact: Path,
    result: "ResultMessage",
    *,
    duration_ms: int | None = None,
) -> str:
    """Format the per-phase one-liner shown after a successful run.

    `duration_ms` overrides the SDK's per-query measurement — pass the
    phase wall-clock for phases that do additional work after the
    agent returns (Phase 6). When None, falls back to
    `result.duration_ms`.
    """
    shown_ms = duration_ms if duration_ms is not None else result.duration_ms
    return (
        f"\nPhase {phase_number} done — {artifact} "
        f"(${result.total_cost_usd:.2f}, {shown_ms / 1000:.1f}s, "
        f"{result.num_turns} turns)"
    )
