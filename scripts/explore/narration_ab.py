"""Throwaway spike — Phase-2 narration A/B (AGENT_SDK_PORTABILITY.md).

The model-comparison spike tested scripting + repair (small models'
strength). This isolates the OPPOSITE: prose quality — the Phase-2
narration the user actually watches, and the most model-sensitive work
in the pipeline.

It feeds each model the REAL phase2 narration rules (read from
prompts/phase2.md), the app one-pager, and one chapter's already-planned
scenes (titles + actions, narration HIDDEN), then asks only for the
narration per scene. Output is printed side-by-side against the
Claude-pipeline ORIGINAL so a human can judge the prose. No scoring —
prose quality is a read, not a metric.

  python scripts/explore/narration_ab.py --chapter "Find anything, fast" \
      --model anthropic:claude-sonnet-4-6
  python scripts/explore/narration_ab.py --chapter "Find anything, fast" \
      --model openrouter:google/gemini-3.1-flash-lite
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_ai import Agent

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pydantic_ai_spike import resolve_model  # noqa: E402 — reuse routing + .env

ROOT = Path(__file__).resolve().parents[2]
PROJECT = Path("/tmp/m8-l5")  # the live chaptered board (m7-longform restore)


class SceneNarration(BaseModel):
    title: str = Field(description="Echo the scene title you were given")
    narration: str = Field(
        description='Spoken narration for this scene, or "" if silent'
    )


class ChapterNarration(BaseModel):
    scenes: list[SceneNarration]


def phase2_rules() -> str:
    """The real narration guidance from the pipeline's phase2 prompt —
    everything except the JSON output-format block (we use a schema)."""
    text = (ROOT / "src/instantdemo/prompts/phase2.md").read_text()
    # Drop the "## Output format" section; keep the narration rules,
    # anti-patterns, and grounding guidance.
    out = []
    skip = False
    for line in text.splitlines():
        if line.startswith("## Output format"):
            skip = True
        elif line.startswith("## ") and skip:
            skip = False
        if not skip:
            out.append(line)
    return "\n".join(out)


def load_chapter(name: str) -> list[dict]:
    doc = json.loads((PROJECT / ".instantdemo/storyboard.json").read_text())
    return [s for s in doc["scenes"] if s.get("section") == name]


def run(model_spec: str, chapter: str) -> ChapterNarration:
    scenes = load_chapter(chapter)
    one_pager = ""
    pc = PROJECT / "product-context.md"
    if pc.exists():
        one_pager = pc.read_text().strip()
    scene_lines = "\n".join(
        f"  {i + 1}. title={s['title']!r}  action={s.get('action')}"
        for i, s in enumerate(scenes)
    )
    agent = Agent(
        resolve_model(model_spec),
        output_type=ChapterNarration,
        retries=2,
        instructions=(
            "You write the spoken narration for one chapter of a product "
            "demo video. Follow these rules exactly:\n\n"
            f"{phase2_rules()}\n\n"
            "--- The app ---\n"
            f"{one_pager}\n\n"
            f"--- Chapter: {chapter!r} ---\n"
            "These scenes are already planned (the action is fixed). Write "
            "ONLY the narration for each, in order. Match the count and "
            "echo each title:\n"
            f"{scene_lines}"
        ),
    )
    result = agent.run_sync("Write the narration for this chapter.")
    return result.output


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="anthropic:claude-sonnet-4-6")
    ap.add_argument("--chapter", default="Find anything, fast")
    args = ap.parse_args()

    originals = load_chapter(args.chapter)
    out = run(args.model, args.chapter)

    print(f"\n{'=' * 70}\nMODEL: {args.model}\nCHAPTER: {args.chapter}\n{'=' * 70}")
    for i, sc in enumerate(out.scenes):
        orig = originals[i]["narration"] if i < len(originals) else "(none)"
        print(f"\nScene {i + 1}: {sc.title}")
        print(f"  ORIGINAL (Claude pipeline): {orig!r}")
        print(f"  {args.model.split(':')[0].upper():9}: {sc.narration!r}")


if __name__ == "__main__":
    main()
