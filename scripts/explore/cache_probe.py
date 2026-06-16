"""Throwaway probe — does Pydantic AI + CachePoint preserve the M7
"paid once" prompt-caching economics? (M9 plan, Step-0 de-risk.)

Simulates a multi-call phase (like Phase 2: heavy prefix once, then short
continuations sharing it). Call 1 carries a large prefix ending in a
CachePoint; call 2 continues the SAME conversation (message_history).
If caching works, call 2's usage shows cache_READ tokens ~ the prefix
size (billed ~10%) instead of re-paying full input.

  python scripts/explore/cache_probe.py --model anthropic:claude-sonnet-4-6
  python scripts/explore/cache_probe.py --model openrouter:deepseek/deepseek-chat-v3.1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic_ai import Agent, CachePoint

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pydantic_ai_spike import resolve_model  # noqa: E402 — reuse routing + .env

# A heavy, stable prefix (~3k+ tokens) — stands in for phase-1 analysis +
# scene rules that every chapter call in Phase 2 shares.
PREFIX = (
    "You are planning a product demo film. The following is fixed context "
    "shared across every planning call; treat it as background.\n\n"
    + (
        "Codebase analysis: the app is a local Evernote viewer with a note "
        "list, a live count pill, full-text search over titles and bodies, a "
        "reader pane with formatted content and metadata, an attachments "
        "view with downloadable files, and a sources dropdown that filters "
        "by export file. It runs at localhost with no account or cloud. "
    ) * 40  # repeat to exceed the 1024-token min cacheable size comfortably
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="anthropic:claude-sonnet-4-6")
    args = ap.parse_args()
    agent = Agent(resolve_model(args.model))

    # Call 1: heavy prefix + CachePoint, tiny output.
    r1 = agent.run_sync(
        [PREFIX, CachePoint(), "Reply with exactly: OUTLINE"]
    )
    u1 = r1.usage

    # Call 2: continue the SAME conversation; prefix should be cache-read.
    r2 = agent.run_sync(
        "Reply with exactly: CHAPTER1", message_history=r1.all_messages()
    )
    u2 = r2.usage

    def row(label, u):
        print(
            f"  {label}: input={u.input_tokens}  output={u.output_tokens}  "
            f"cache_write={getattr(u, 'cache_write_tokens', None)}  "
            f"cache_read={getattr(u, 'cache_read_tokens', None)}"
        )

    print(f"\nmodel={args.model}  (prefix ~{len(PREFIX) // 4} tokens est.)")
    row("call 1 (prefix + CachePoint)", u1)
    row("call 2 (continuation)        ", u2)
    cr = getattr(u2, "cache_read_tokens", 0) or 0
    print(
        "\nVERDICT: "
        + (
            f"CACHING WORKS — call 2 read {cr} cached tokens (prefix paid once)."
            if cr > 500
            else "NO CACHE HIT on call 2 — prefix would be re-paid each call."
        )
    )


if __name__ == "__main__":
    main()
