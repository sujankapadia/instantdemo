"""Prototype iteration 2: HYBRID runner-driven Phase 1 for an SPA.

model plans interactions (1 call) -> runner executes deterministically,
screenshotting each resulting screen -> model interprets (1 call).

Validates the design on evernote (a JS SPA where naive link-crawl found
only 1 screen). Standalone; does not touch the pipeline.
"""
import asyncio, time
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field
from dotenv import load_dotenv
load_dotenv("/Users/user/dev/personal/instantdemo/.env")
from playwright.sync_api import sync_playwright
from instantdemo.agent_backend import PydanticAIBackend
from instantdemo.phases.analyze import ExplorePayload, _validate_payload, _normalized_proposal

import os
START = os.environ.get("M9_URL", "http://localhost:8001")
GOAL = os.environ.get("M9_GOAL", "Give a tour of this app's main features and what it does")
EXP = Path("/tmp/m9-p1-proto/exploration"); EXP.mkdir(parents=True, exist_ok=True)
for p in EXP.glob("*.png"): p.unlink()


class Step(BaseModel):
    action: str = Field(description="one of: click, fill, select, goto")
    target: str = Field(description="visible text / placeholder / label of the element")
    value: str = Field(default="", description="text to fill, option to select, or url to goto")
    reaches: str = Field(default="", description="what screen/state this step reveals")


class ExplorePlan(BaseModel):
    steps: list[Step] = Field(description="ordered interactions to reveal every distinct screen")


import re as _re
def snapshot(page, idx, label):
    """Screenshot + extract text from the current SPA state."""
    label = _re.sub(r"[^a-zA-Z0-9]+", "-", label).strip("-").lower()[:20] or "screen"
    shot = f"{idx:03d}-{label}.png"
    try:
        page.wait_for_timeout(700)
        page.screenshot(path=str(EXP / shot), full_page=False)
    except Exception:
        shot = None
    title = page.title()
    headings = page.eval_on_selector_all(
        "h1,h2,h3,.card-title,[class*=title]",
        "els => els.map(e=>e.innerText.trim()).filter(Boolean).slice(0,8)")
    text = page.evaluate("() => document.body.innerText.slice(0,700)")
    return {"screenshot": shot, "title": title, "headings": headings,
            "text": (text or '').replace('\n', ' ')[:500], "label": label}


def interactive_dump(page):
    """Generic surface of interactive elements — roles/text/labels, no
    app-specific selectors. Works on any app."""
    return page.eval_on_selector_all(
        "a,button,[role=button],[role=link],[role=tab],[role=menuitem],"
        "input,textarea,select,[onclick],li,tr,[class*=card],[class*=item],[class*=row]",
        "els => els.map(e=>({tag:e.tagName, role:e.getAttribute('role'),"
        " text:(e.innerText||e.value||e.placeholder||e.getAttribute('aria-label')||'').trim().slice(0,50),"
        " label:(e.labels&&e.labels[0]?e.labels[0].innerText:'')||''}))"
        ".filter(x=>x.text).slice(0,40)")


def _first_visible(locators):
    """First locator that exists and is visible — the generic resolution
    primitive (no app knowledge, just actionability)."""
    for loc in locators:
        try:
            if loc.count() and loc.first.is_visible():
                return loc.first
        except Exception:
            continue
    return None


def resolve_and_act(page, step: Step):
    """GENERIC resolver: map a planned step onto a Playwright action using
    only accessibility/text locators. No app-specific selectors."""
    target = step.target.strip()
    if step.action == "goto":
        page.goto(step.value or START, wait_until="domcontentloaded")
        return f"goto {step.value}"
    if step.action == "fill":
        loc = _first_visible([
            page.get_by_placeholder(target, exact=False),
            page.get_by_label(target, exact=False),
            page.get_by_role("textbox", name=target),
            page.get_by_role("searchbox", name=target),
            page.locator("input[type=search],input[type=text],input:not([type]),textarea"),
        ])
        if not loc:
            raise RuntimeError(f"no fillable input for {target!r}")
        loc.fill(step.value); loc.press("Enter")
        return f"fill '{step.value}'"
    if step.action == "select":
        loc = _first_visible([page.get_by_label(target, exact=False), page.locator("select")])
        if not loc:
            raise RuntimeError(f"no select for {target!r}")
        for attempt in (lambda: loc.select_option(label=step.value),
                        lambda: loc.select_option(value=step.value),
                        lambda: loc.select_option(index=1)):
            try:
                attempt(); break
            except Exception:
                continue
        return f"select '{step.value}'"
    # click — resolve by role then text, all generic. Also try a "core"
    # variant with decorative leading symbols/emoji stripped (models often
    # echo a "📎 Attachments" label verbatim; the accessible name is the word).
    core = _re.sub(r"^[^\w]+", "", target).strip() or target
    cands = []
    for t in dict.fromkeys([target, core]):   # de-dup, preserve order
        cands += [
            page.get_by_role("button", name=t, exact=False),
            page.get_by_role("link", name=t, exact=False),
            page.get_by_role("tab", name=t, exact=False),
            page.get_by_role("menuitem", name=t, exact=False),
            page.get_by_text(t, exact=False),
        ]
    loc = _first_visible(cands)
    if not loc:
        raise RuntimeError(f"no clickable element for {target!r}")
    loc.click()
    return f"click '{target}'"


def run_plan(plan: ExplorePlan):
    screens = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.set_default_timeout(4000)   # fast-fail bad steps (was 30s default)
        page.goto(START, wait_until="domcontentloaded"); page.wait_for_selector("body")
        screens.append(snapshot(page, 1, "home"))
        for i, step in enumerate(plan.steps, start=2):
            try:
                # reset to a clean baseline so each reveal is INDEPENDENT —
                # no prior step can hide the control this one needs.
                page.goto(START, wait_until="domcontentloaded")
                page.wait_for_selector("body")
                did = resolve_and_act(page, step)
                screens.append({**snapshot(page, i, step.reaches.replace(' ', '-')[:20] or f"step{i}"),
                                "did": did, "reaches": step.reaches})
            except Exception as e:
                screens.append({"label": f"step{i}", "error": str(e)[:80], "reaches": step.reaches})
        browser.close()
    return screens


PLAN_PROMPT_TPL = """This is the start page of a running web app at {url}. Here are its
interactive elements (buttons, inputs, nav, cards):

{dump}

The app is a single-page app — navigation happens by interacting, not by URLs.
Plan an ordered list of interactions that reveals every DISTINCT screen a demo
would show (e.g. switch views, run a search, open a detail item).

Rules for `target`: use the EXACT visible text or label of the element from the
list above — that's how the runner finds it (by role/text/placeholder). To open
a list item (e.g. a note), use that item's actual visible title as the target,
NOT a description like "first item". Each step is executed from a fresh page
load, so steps are independent — don't rely on a previous step's state.
Keep it to ~6 focused steps."""


def interpret_prompt(screens):
    lines = ["I executed an exploration plan on a running web app. Screens captured:\n"]
    for s in screens:
        if s.get("error"):
            lines.append(f"- [{s['label']}] FAILED: {s['error']}"); continue
        lines.append(f"### {s['title']} — {s.get('reaches') or s['label']}  [screenshot: {s['screenshot']}]")
        if s["headings"]: lines.append("headings: " + " | ".join(s["headings"]))
        lines.append("text: " + s["text"][:380])
    lines.append(f"\nThe user wants to demo: {GOAL}.\n"
                 "Produce app_model, proposed_intent (goal/audience/tone/focus), screens "
                 "(name+route+screenshot for each above), warnings.")
    return "\n".join(lines)


async def main(dump):
    be = PydanticAIBackend(default_model="openrouter:deepseek/deepseek-chat-v3.1",
                           allowed_roots=[Path("/tmp")], cwd=Path("/tmp"))
    class C: event_emitter = None
    # call 1: plan
    t1 = time.monotonic()
    plan_r = await be.run_structured(C(), PLAN_PROMPT_TPL.format(url=START, dump=dump),
                                     "phase2-plan", output_type=ExplorePlan)
    t_plan = time.monotonic() - t1
    plan = plan_r.output
    print(f"PLAN ({t_plan:.0f}s): {len(plan.steps)} steps")
    for s in plan.steps: print(f"  - {s.action} '{s.target}' {repr(s.value) if s.value else ''} -> {s.reaches}")
    return plan


# --- sync crawl/exec outside asyncio, model calls inside ---
t0 = time.monotonic()
with sync_playwright() as _p:
    _b = _p.chromium.launch(); _pg = _b.new_page()
    _pg.goto(START, wait_until="domcontentloaded"); _pg.wait_for_selector("body")
    DUMP = "\n".join(
        f"- {x['tag']}{('/'+x['role']) if x.get('role') else ''} {repr(x['text'])}"
        + (f" label={x['label']!r}" if x.get('label') else '')
        for x in interactive_dump(_pg))
    _b.close()

plan = asyncio.run(main(DUMP))
t_exec0 = time.monotonic()
screens = run_plan(plan)
t_exec = time.monotonic() - t_exec0
print(f"\nEXEC ({t_exec:.0f}s): {len(screens)} screens")
for s in screens:
    print("  ", s.get("title") or s.get("error"), "|", s.get("did") or s.get("reaches"))


async def finish():
    be = PydanticAIBackend(default_model="openrouter:deepseek/deepseek-chat-v3.1",
                           allowed_roots=[Path("/tmp")], cwd=Path("/tmp"))
    class C: event_emitter = None
    t = time.monotonic()
    r = await be.run_structured(C(), interpret_prompt(screens), "phase2-interp", output_type=ExplorePayload)
    payload = r.output.model_dump()
    print(f"\nINTERPRET ({time.monotonic()-t:.0f}s)")
    print("TOTAL WALLCLOCK: %.0fs" % (time.monotonic()-t0))
    print("validate:", _validate_payload(payload, EXP) or "OK")
    prop = _normalized_proposal(payload)
    print("\napp_model:", payload["app_model"][:280])
    print("goal:", prop["goal"])
    print("focus:", prop["focus"])
    print("screens:", [s.get("name") for s in payload.get("screens", [])])
    print("warnings:", payload.get("warnings"))

asyncio.run(finish())
