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
import json
import sys
import tempfile
import time
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_ai import Agent, FilteredToolset

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pydantic_ai_spike import Jail, make_toolset, resolve_model  # noqa: E402

APP_URL = "http://localhost:8001"
PROJECT = Path("/tmp/m8-l5")


def load_brief() -> str:
    """The user's real brief (goal/focus/excludes), fed to Phase 1 the
    way analyze.py does (src/instantdemo/phases/analyze.py:87-94)."""
    intent = json.loads((PROJECT / "intent.json").read_text())
    lines = []
    goal = (intent.get("goal") or "").strip()
    if goal:
        lines.append(f"The user wants to demo: {goal}")
    if intent.get("focus"):
        lines.append("Focus on: " + "; ".join(intent["focus"]))
    if intent.get("excludes"):
        lines.append("Exclude (do NOT propose these): " + "; ".join(intent["excludes"]))
    return "\n".join(lines)


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


# An explicit exploration protocol — supplies the initiative a capable
# agentic model self-generates, so we can test whether the Phase-1 depth
# gap is disposition (promptable) or capability (not).
EXPLORE_PROTOCOL = (
    "\n\nExplore THOROUGHLY before proposing — work this checklist:\n"
    "- Enumerate every nav link, tab, and button; click each and note "
    "what changes.\n"
    "- Run at least 5 DIFFERENT searches, including words unlikely to be "
    "in any title, to test whether search reads note bodies. Report the "
    "actual result count for each.\n"
    "- Open at least 3 different notes and read what the detail view "
    "shows (metadata, formatting, attachments).\n"
    "- Try every dropdown/filter (e.g. source files); select each option "
    "and report the count it shows.\n"
    "- Look specifically for an attachments view and any downloadable "
    "files.\n"
    "- Inspect the page HTML / network requests for structure you can't "
    "see in the UI (endpoints, debounce, hidden fields).\n"
    "Report the real counts and names you observed, not approximations."
)


def run(
    model_spec: str, guided: bool = False, brief: bool = False
) -> tuple[IntentProposal | None, object, float, str | None]:
    brief_block = (
        f"\n\n--- The user's brief ---\n{load_brief()}\n"
        "Scope your exploration to the brief: prioritise the focus areas, "
        "honor the excludes, and propose a demo that serves this goal.\n"
        if brief
        else ""
    )
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
                + brief_block
                + (EXPLORE_PROTOCOL if guided else "")
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
    ap.add_argument("--guided", action="store_true",
                    help="add the explicit exploration checklist")
    ap.add_argument("--brief", action="store_true",
                    help="feed the user's real goal/focus/excludes (scoped)")
    args = ap.parse_args()

    out, usage, secs, err = run(args.model, guided=args.guided, brief=args.brief)
    mode = "+".join(
        [m for m, on in (("brief", args.brief), ("guided", args.guided)) if on]
    ) or "unguided"
    print(f"\n{'=' * 70}\nMODEL: {args.model}  [{mode}]  ({secs:.0f}s)\n{'=' * 70}")
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
