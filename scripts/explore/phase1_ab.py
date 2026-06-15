"""Throwaway spike — Phase-1 A/B (AGENT_SDK_PORTABILITY.md).

Phase 1 is the hybrid: drive the LIVE app (Playwright via bash) to
explore it, THEN propose a demo intent — agentic browser-driving (cheap
models strong) + judgment/synthesis grounded in what was seen (cheap
models weak, per Phase 2). This harness reuses the spike's jailed-bash
tool, asks each model to explore localhost:8001 and propose an intent,
and prints it for comparison. The test: did it actually explore (tool
calls), and is the proposal GROUNDED in the real app (note list, search,
attachments, sources, local/private) vs invented?

  python scripts/explore/phase1_ab.py --model anthropic:claude-sonnet-4-6
  python scripts/explore/phase1_ab.py --model openrouter:deepseek/deepseek-chat-v3.1
  python scripts/explore/phase1_ab.py --model openrouter:google/gemini-3.1-flash-lite
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_ai import Agent, FilteredToolset

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pydantic_ai_spike import Jail, make_toolset, resolve_model  # noqa: E402

APP_URL = "http://localhost:8001"


class IntentProposal(BaseModel):
    title: str = Field(description="A short demo title")
    goal: str = Field(description="What the demo should show — the core value")
    audience: str
    flows: list[str] = Field(
        description="Demo-worthy flows, each grounded in an observed feature"
    )
    screens: list[str] = Field(description="Key screens/views you actually saw")
    warnings: list[str] = Field(
        default_factory=list,
        description="Caveats for a demo (e.g. volatile data, destructive actions)",
    )


def run(model_spec: str) -> tuple[IntentProposal | None, object, float, str | None]:
    with tempfile.TemporaryDirectory(prefix="pai-p1-") as td:
        jail_dir = Path(td)
        base = make_toolset(jail_dir)
        jail = Jail(base, jail_dir)
        allowed = FilteredToolset(jail, lambda ctx, t: t.name == "bash")
        agent = Agent(
            resolve_model(model_spec),
            output_type=IntentProposal,
            retries=2,
            instructions=(
                "You are scouting a web app to plan a demo video. The app is "
                f"at {APP_URL}. Use the `bash` tool to drive Playwright (sync "
                "API, headless chromium) in your sandbox: open the app, "
                "screenshot, click around, read what each screen shows. "
                "Explore enough to understand what the app actually DOES — its "
                "real features and data. THEN propose the demo: title, goal, "
                "audience, the flows worth showing, the key screens, and any "
                "warnings. GROUND everything in what you observed — do NOT "
                "invent features, counts, or data you did not see."
            ),
            toolsets=[allowed],
        )
        t0 = time.monotonic()
        err = None
        out = None
        usage = None
        try:
            result = agent.run_sync("Explore the app and propose the demo intent.")
            out, usage = result.output, result.usage
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
        return out, usage, time.monotonic() - t0, err


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="anthropic:claude-sonnet-4-6")
    args = ap.parse_args()

    out, usage, secs, err = run(args.model)
    print(f"\n{'=' * 70}\nMODEL: {args.model}   ({secs:.0f}s)\n{'=' * 70}")
    if err:
        print(f"ERROR: {err}")
        return
    tools = getattr(usage, "tool_calls", None)
    print(f"tool calls (exploration): {tools}\n")
    print(f"TITLE:    {out.title}")
    print(f"GOAL:     {out.goal}")
    print(f"AUDIENCE: {out.audience}")
    print("FLOWS:")
    for f in out.flows:
        print(f"  • {f}")
    print("SCREENS:")
    for s in out.screens:
        print(f"  • {s}")
    if out.warnings:
        print("WARNINGS:")
        for w in out.warnings:
            print(f"  • {w}")


if __name__ == "__main__":
    main()
