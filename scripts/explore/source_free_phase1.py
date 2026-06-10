#!/usr/bin/env python3
"""Prototype: source-free Phase 1 (Understand) via live-app exploration.

Tests the explore-first hypothesis from ARCHITECTURE_RETHINK.md /
PRODUCT_DIRECTION.md: can an agent with NO source access build a
phase1.md-quality model of an app purely by driving the live app
with headless Playwright?

The agent gets a Bash-only tool allowlist (enforced with the same
PreToolUse-hook mechanism as agent_client.PhaseDispatcher) and runs
from an empty temp directory so it has no incidental access to the
app's source tree. Exploration is prompt-constrained to read-only
interactions (no destructive clicks) — a production version would
need stronger guardrails; this is a prototype.

Usage:
    python scripts/explore/source_free_phase1.py \
        --url http://127.0.0.1:8001/ \
        --goal "Show the notes list and open a note" \
        --out scripts/explore/out/source-free-phase1-evernote.md

Compare the output against a source-based baseline, e.g.
fixtures/<name>/.instantdemo/phase1.md for the same app.

Cost: roughly comparable to a pipeline Phase 4 run (~$0.3-0.6,
~2-5 min), since the agent drives Playwright via Bash.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    HookMatcher,
    ResultMessage,
    TextBlock,
)

ALLOWED_TOOLS = frozenset({"Bash"})

# Cap injected docs so a long README can't crowd out the task.
DOCS_MAX_CHARS = 10_000

DOCS_SECTION_TEMPLATE = """\
The user has provided product documentation for this app (e.g. a \
README or product one-pager). Use it for framing and vocabulary — \
what the product is called, what its features are named, who it's \
for. The documentation may be stale or describe a different \
deployment: where it conflicts with what you observe in the live \
app, TRUST THE LIVE APP and note the discrepancy.

<product-documentation>
{docs}
</product-documentation>

"""

PROMPT_TEMPLATE = """\
The user wants to demo: {goal}

{docs_section}\
You are analyzing a RUNNING web application at {url} to understand \
what it does and how it works. You have no access to its source \
code — build your understanding entirely by observing and using the \
live app with headless Playwright (Python) scripts run via Bash.

Suggested approach:

1. **Load the start page**: capture the page title, main headings, \
navigation links, and visible copy.
2. **Enumerate the screens**: follow each navigation link (and any \
obvious routes you discover along the way). For each screen, record \
its URL, what it's for, and the main UI regions — lists, tables, \
charts, forms, buttons, search boxes.
3. **Go deep on demo-relevant screens**: for the screens the demo \
goal needs, observe what data is displayed and what's clickable. \
Follow one representative click-through (e.g. open a list item) to \
see where it leads.
4. **Note access details**: port, any login or auth wall, anything \
that must be true before a demo (data that must exist, services \
that must be running).

Safety rules (important):
- Read-only exploration. Do NOT trigger destructive or data-mutating \
controls: no delete/remove buttons, no imports or uploads, no form \
submissions. Navigation clicks, opening list items, scrolling, and \
reading are all fine.
- Pages may use Server-Sent Events or live polling: do not wait for \
networkidle. Use domcontentloaded plus wait_for_selector instead.

When you're done, summarize in markdown: what the app does, the main \
screens/features (one line each on what they render), how to access \
the app, and a section of demo-relevant details for the flow above — \
including anything a demo should verify exists before recording.
"""


def _make_bash_only_hook():
    """PreToolUse hook allowing only ALLOWED_TOOLS.

    Same mechanism as agent_client.PhaseDispatcher.hook — with
    permission_mode=bypassPermissions, a PreToolUse hook is the
    reliable way to enforce a tool allowlist.
    """

    async def hook(
        input_data: dict[str, Any],
        _tool_use_id: str | None,
        _ctx: Any,
    ) -> dict[str, Any]:
        tool_name = input_data.get("tool_name", "")
        if tool_name in ALLOWED_TOOLS:
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
                    f"Tool {tool_name!r} not permitted in source-free "
                    f"exploration; allowed: {sorted(ALLOWED_TOOLS)}"
                ),
            }
        }

    return hook


async def run(url: str, goal: str, out: Path, docs: Path | None = None) -> int:
    # Empty cwd: the agent must not be able to stumble onto the
    # app's source tree via relative paths.
    cwd = tempfile.mkdtemp(prefix="source-free-phase1-")

    options = ClaudeAgentOptions(
        cwd=cwd,
        permission_mode="bypassPermissions",
        hooks={
            "PreToolUse": [
                # Same cast issue as agent_client.make_agent_client —
                # Pyright can't unify our return dict with HookJSONOutput.
                HookMatcher(matcher=None, hooks=[_make_bash_only_hook()])  # type: ignore[list-item]
            ],
        },
    )

    docs_section = ""
    if docs is not None:
        docs_text = docs.read_text()
        if len(docs_text) > DOCS_MAX_CHARS:
            docs_text = (
                docs_text[:DOCS_MAX_CHARS] + "\n\n[... truncated ...]"
            )
        docs_section = DOCS_SECTION_TEMPLATE.format(docs=docs_text)

    prompt = PROMPT_TEMPLATE.format(
        url=url, goal=goal, docs_section=docs_section
    )
    print(f"[proto] cwd:  {cwd}")
    print(f"[proto] url:  {url}")
    print(f"[proto] goal: {goal}")
    print(f"[proto] docs: {docs if docs else '(none)'}")
    print("[proto] connecting...")

    started = time.monotonic()
    text_chunks: list[str] = []
    result = None

    client = ClaudeSDKClient(options=options)
    await client.connect()
    try:
        await client.query(prompt, session_id="source-free-phase1")
        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        print(block.text, flush=True)
                        text_chunks.append(block.text)
                    elif type(block).__name__ == "ToolUseBlock":
                        cmd = (getattr(block, "input", {}) or {}).get(
                            "command", ""
                        )
                        first = cmd.strip().splitlines()[0] if cmd else ""
                        print(f"[tool] Bash: {first[:120]}", flush=True)
            elif isinstance(msg, ResultMessage):
                result = msg
                break
    finally:
        await client.disconnect()

    wall_s = time.monotonic() - started
    if result is None:
        print("[proto] FAIL: no ResultMessage", file=sys.stderr)
        return 1
    if result.is_error:
        print(
            f"[proto] FAIL: agent errored: {getattr(result, 'result', '')}",
            file=sys.stderr,
        )
        return 1

    out.parent.mkdir(parents=True, exist_ok=True)
    header = (
        f"<!-- source-free phase1 prototype | url: {url} | "
        f"docs: {docs if docs else 'none'} | "
        f"cost: ${result.total_cost_usd:.3f} | wall: {wall_s:.0f}s | "
        f"turns: {result.num_turns} -->\n\n"
    )
    out.write_text(header + "\n".join(text_chunks) + "\n")
    print(
        f"\n[proto] PASS — {out} "
        f"(${result.total_cost_usd:.3f}, {wall_s:.0f}s, "
        f"{result.num_turns} turns)"
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", required=True, help="Live app URL")
    ap.add_argument("--goal", required=True, help="Demo goal (intent.goal)")
    ap.add_argument(
        "--out",
        required=True,
        type=Path,
        help="Where to write the resulting markdown artifact",
    )
    ap.add_argument(
        "--docs",
        type=Path,
        default=None,
        help=(
            "Optional product doc (README, one-pager) to inject into "
            "the prompt for framing/vocabulary — simulates the user "
            "pasting their product docs. Not source code."
        ),
    )
    args = ap.parse_args()
    return asyncio.run(run(args.url, args.goal, args.out, args.docs))


if __name__ == "__main__":
    sys.exit(main())
