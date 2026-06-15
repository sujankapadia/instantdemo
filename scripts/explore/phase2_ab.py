"""Throwaway spike — FULL Phase-2 A/B (AGENT_SDK_PORTABILITY.md).

The narration A/B tested isolated single-chapter prose. This reproduces
the WHOLE Phase-2 flow the pipeline runs — outline -> per-chapter
narration -> continuity pass — on each model, so the comparison
captures the two things the isolated test couldn't: the chapter ARC
(outline) and the CONTINUITY pass (whole-film attention: catching
repeated openers / claims across chapters). Uses the real prompts
(phase2_outline.md, phase2.md, the continuity prompt) and the real
Evernote inputs (intent.json, phase1.md, product-context.md from the
m8-l5 board). Prints each model's full chaptered film for a blind read;
reports what the continuity pass changed.

  python scripts/explore/phase2_ab.py --model anthropic:claude-sonnet-4-6
  python scripts/explore/phase2_ab.py --model openrouter:google/gemini-3.1-flash-lite
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_ai import Agent

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pydantic_ai_spike import resolve_model  # noqa: E402
from narration_ab import phase2_rules  # noqa: E402 — phase2.md minus output-format

ROOT = Path(__file__).resolve().parents[2]
PROJECT = Path("/tmp/m8-l5")


# ── schemas (the three beats) ────────────────────────────────────────
class Chapter(BaseModel):
    name: str
    purpose: str
    est_scenes: int = Field(ge=1, le=12)


class Outline(BaseModel):
    title: str
    summary: str
    chapters: list[Chapter]


class Scene(BaseModel):
    title: str
    narration: str = Field(description='spoken narration, or "" if silent')
    action: str


class ChapterScenes(BaseModel):
    scenes: list[Scene]


class Continuity(BaseModel):
    explanation: str
    rewrites: dict[str, str] = Field(
        default_factory=dict,
        description="1-based global scene number -> new narration; empty if none",
    )


# ── inputs (faithful to phases/narrate.py) ───────────────────────────
def inputs_header() -> str:
    intent = json.loads((PROJECT / "intent.json").read_text())
    lines: list[str] = []
    if intent.get("goal"):
        lines += [f"The user wants to demo: {intent['goal']}", ""]
    lines.append(f"Tone: {intent.get('tone') or 'friendly, unhurried'}")
    lines.append(f"Audience: {intent.get('audience') or 'general'}")
    if intent.get("focus"):
        lines.append("Focus on: " + "; ".join(intent["focus"]))
    if intent.get("excludes"):
        lines.append("Exclude: " + "; ".join(intent["excludes"]))
    return "\n".join(lines)


def outline_text(o: Outline) -> str:
    lines = [f"The film: {o.title} — {o.summary}"]
    for i, ch in enumerate(o.chapters, 1):
        lines.append(f"  {i}. {ch.name} — {ch.purpose}")
    return "\n".join(lines)


# ── the three beats ──────────────────────────────────────────────────
def run_phase2(model_spec: str) -> dict:
    model = resolve_model(model_spec)
    phase1 = (PROJECT / ".instantdemo/phase1.md").read_text()
    one_pager = (PROJECT / "product-context.md").read_text().strip()
    hdr = inputs_header()

    # Beat 1 — outline (the arc)
    outline = Agent(
        model, output_type=Outline, retries=2,
        instructions=(
            f"{hdr}\n\n--- Codebase analysis (Phase 1) ---\n{phase1}\n---\n\n"
            + (ROOT / "src/instantdemo/prompts/phase2_outline.md").read_text()
        ),
    ).run_sync("Outline the film's chapters.").output

    # Beat 2 — per-chapter narration (each knows the whole arc + the
    # previous chapter's last scene, like the real per-chapter call)
    rules = phase2_rules()
    arc = outline_text(outline)
    chapters: list[dict] = []
    prev_last = None
    for i, ch in enumerate(outline.chapters):
        boundary = (
            f"\nThe previous chapter ended on: {prev_last!r}. Continue "
            "naturally from there.\n" if prev_last else ""
        )
        scenes = Agent(
            model, output_type=ChapterScenes, retries=2,
            instructions=(
                f"You write one chapter of a demo film.\n\n{rules}\n\n"
                f"--- The app ---\n{one_pager}\n\n--- The whole film ---\n{arc}\n"
                f"{boundary}\n--- Your chapter: {ch.name!r} ---\n{ch.purpose}\n"
                f"Plan about {ch.est_scenes} scenes. Write title, narration "
                '(or "" if silent), and a high-level action for each.'
            ),
        ).run_sync(f"Plan chapter {ch.name!r}.").output
        chapters.append({"name": ch.name, "scenes": [s.model_dump() for s in scenes.scenes]})
        # boundary = last non-silent narration of this chapter
        for s in reversed(scenes.scenes):
            if s.narration.strip():
                prev_last = s.narration
                break

    # Beat 3 — continuity pass (whole-film attention)
    flat = [(ci, si, s) for ci, c in enumerate(chapters) for si, s in enumerate(c["scenes"])]
    numbered = "\n".join(
        f"{n}. [{chapters[ci]['name']}] {s['narration']!r}"
        for n, (ci, si, s) in enumerate(flat, 1)
        if s["narration"].strip()
    )
    cont = Agent(
        model, output_type=Continuity, retries=2,
        instructions=(
            "You are the script editor reading a demo film's full narration "
            "in one sitting. The chapters were written separately; make them "
            "read as ONE film. Look ONLY for: repetitive chapter openers, "
            "information repeated across chapters, broken transitions, global "
            "claims duplicated per chapter. Do NOT restyle narration that "
            "already works. Return ONLY changed scenes (1-based global number "
            "-> new narration), same approximate length, plain text. Empty if "
            "it already reads as one film.\n\n--- Full narration ---\n" + numbered
        ),
    ).run_sync("Smooth the film into one read.").output

    for num_str, new_text in cont.rewrites.items():
        try:
            n = int(num_str)
        except ValueError:
            continue
        if 1 <= n <= len(flat):
            ci, si, _ = flat[n - 1]
            chapters[ci]["scenes"][si]["narration"] = new_text

    return {"outline": outline, "chapters": chapters, "continuity": cont}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="anthropic:claude-sonnet-4-6")
    args = ap.parse_args()

    film = run_phase2(args.model)
    o: Outline = film["outline"]
    print(f"\n{'=' * 72}\nMODEL: {args.model}\nFILM: {o.title} — {o.summary}\n{'=' * 72}")
    print(f"\nOUTLINE ({len(o.chapters)} chapters):")
    for ch in o.chapters:
        print(f"  • {ch.name} ({ch.est_scenes}) — {ch.purpose}")
    n = 0
    for c in film["chapters"]:
        print(f"\n── {c['name']} ──")
        for s in c["scenes"]:
            n += 1
            tag = "" if s["narration"].strip() else "  (silent)"
            print(f"  {n}. [{s['action']}] {s['title']}{tag}")
            if s["narration"].strip():
                print(f"     {s['narration']}")
    cont: Continuity = film["continuity"]
    print(f"\nCONTINUITY PASS: {len(cont.rewrites)} rewrite(s) — {cont.explanation}")


if __name__ == "__main__":
    main()
