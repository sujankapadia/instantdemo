"""Prototype iteration 3: PATH-based runner-driven Phase 1.

Fixes the reset-to-baseline limitation. The plan is:
  - setup: an optional shared prefix (e.g. login), REPLAYED before each
    path (mirrors Phase 4's verified-prefix replay) — handles auth.
  - paths: independent exploration paths, each an ordered sequence of
    steps (chained within → handles DEPTH; isolated between → no
    cross-contamination).

model plans (1 call) -> runner executes paths deterministically -> model
interprets (1 call). Generic resolver, no app-specific selectors.
"""
import asyncio, os, re as _re, time
from pathlib import Path as P
from pydantic import BaseModel, Field
from dotenv import load_dotenv
load_dotenv("/Users/user/dev/personal/instantdemo/.env")
from playwright.sync_api import sync_playwright
from instantdemo.agent_backend import PydanticAIBackend
from instantdemo.phases.analyze import ExplorePayload, _validate_payload, _normalized_proposal

START = os.environ["M9_URL"]
GOAL = os.environ.get("M9_GOAL", "Give a tour of this app's main features")
EXP = P("/tmp/m9-p1-proto/exploration"); EXP.mkdir(parents=True, exist_ok=True)
for p in EXP.glob("*.png"): p.unlink()


class Step(BaseModel):
    action: str = Field(description="one of: click, fill, select, goto")
    target: str = Field(description="exact visible text / placeholder / label")
    value: str = Field(default="", description="text to fill, option, or url")


class Path(BaseModel):
    steps: list[Step] = Field(description="ordered steps from the baseline; chain to reach DEEP screens")
    reaches: str = Field(default="", description="the distinct screen this path reveals")


class ExplorePlan(BaseModel):
    setup: list[Step] = Field(default_factory=list, description="shared login/setup prefix, replayed before each path; empty if no auth needed")
    paths: list[Path] = Field(description="independent exploration paths")


def snapshot(page, idx, label):
    label = _re.sub(r"[^a-zA-Z0-9]+", "-", label).strip("-").lower()[:20] or "screen"
    shot = f"{idx:03d}-{label}.png"
    try:
        page.wait_for_timeout(600); page.screenshot(path=str(EXP / shot), full_page=False)
    except Exception:
        shot = None
    return {"screenshot": shot, "title": page.title(),
            "headings": page.eval_on_selector_all("h1,h2,h3,[class*=title]",
                "els=>els.map(e=>e.innerText.trim()).filter(Boolean).slice(0,8)"),
            "text": (page.evaluate("()=>document.body.innerText.slice(0,700)") or '').replace('\n', ' ')[:500],
            "label": label}


def interactive_dump(page):
    return page.eval_on_selector_all(
        "a,button,[role=button],[role=link],[role=tab],input,textarea,select,[onclick],li,tr,[class*=card],[class*=item]",
        "els=>els.map(e=>({tag:e.tagName,text:(e.innerText||e.value||e.placeholder||e.getAttribute('aria-label')||'').trim().slice(0,50)})).filter(x=>x.text).slice(0,45)")


def _first_visible(locs):
    for loc in locs:
        try:
            if loc.count() and loc.first.is_visible(): return loc.first
        except Exception: continue
    return None


def resolve_and_act(page, step):
    target = step.target.strip()
    if step.action == "goto":
        page.goto(step.value or START, wait_until="domcontentloaded"); return
    if step.action == "fill":
        loc = _first_visible([page.get_by_placeholder(target, exact=False),
            page.get_by_label(target, exact=False), page.get_by_role("textbox", name=target),
            page.locator("input[type=search],input[type=text],input[type=password],input:not([type]),textarea")])
        if not loc: raise RuntimeError(f"no input for {target!r}")
        loc.fill(step.value); return
    if step.action == "select":
        loc = _first_visible([page.get_by_label(target, exact=False), page.locator("select")])
        if not loc: raise RuntimeError(f"no select for {target!r}")
        for a in (lambda: loc.select_option(label=step.value), lambda: loc.select_option(value=step.value), lambda: loc.select_option(index=1)):
            try: a(); break
            except Exception: continue
        return
    core = _re.sub(r"^[^\w]+", "", target).strip() or target
    cands = []
    for t in dict.fromkeys([target, core]):
        cands += [page.get_by_role("button", name=t, exact=False), page.get_by_role("link", name=t, exact=False),
                  page.get_by_role("tab", name=t, exact=False), page.get_by_text(t, exact=False)]
    loc = _first_visible(cands)
    if not loc: raise RuntimeError(f"no clickable element for {target!r}")
    loc.click()


def run_plan(plan):
    screens, failures = [], 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(); page = ctx.new_page(); page.set_default_timeout(4000)
        page.goto(START, wait_until="domcontentloaded"); page.wait_for_selector("body")
        # run setup once to discover the authenticated baseline url
        for st in plan.setup:
            try: resolve_and_act(page, st); page.wait_for_timeout(400)
            except Exception as e: print(f"  [setup] {st.action} {st.target!r} failed: {str(e)[:60]}")
        page.wait_for_timeout(500)
        baseline_url = page.url
        screens.append({**snapshot(page, 1, "baseline"), "reaches": "home / baseline"})
        for i, path in enumerate(plan.paths, start=2):
            try:
                page.goto(START, wait_until="domcontentloaded"); page.wait_for_selector("body")
                for st in plan.setup:                       # prefix replay (auth)
                    try: resolve_and_act(page, st); page.wait_for_timeout(300)
                    except Exception: pass
                for st in path.steps:                       # chained path (depth)
                    resolve_and_act(page, st); page.wait_for_timeout(300)
                screens.append({**snapshot(page, i, path.reaches), "reaches": path.reaches,
                                "did": " → ".join(f"{s.action} {s.target}" for s in path.steps)})
            except Exception as e:
                failures += 1
                screens.append({"label": f"path{i}", "error": str(e)[:80], "reaches": path.reaches,
                                "did": " → ".join(f"{s.action} {s.target}" for s in path.steps)})
        browser.close()
    return screens, failures


PLAN_TPL = """Start page of a web app at {url}. Interactive elements:

{dump}

Goal: {goal}

Plan exploration as JSON:
- `setup`: if the app needs login to reach its features, the steps to log in (use any
  credentials VISIBLE on the page; many demo apps print them). Empty list if no login needed.
- `paths`: 4-6 INDEPENDENT exploration paths revealing distinct TOP-LEVEL screens. Keep each
  path SHALLOW — ONE step is best, at most TWO. Reveal the main screens (sections, a search,
  open one representative item) with the FEWEST clicks. Do NOT plan deep multi-step workflows
  (e.g. a full checkout) — you can't see intermediate pages, so deep guesses fail. Use EXACT
  visible text for targets, and ONLY the text (not the element's tag).
Each path runs from a fresh baseline with setup replayed, so paths don't interfere."""


def interpret_prompt(screens):
    out = ["I executed an exploration plan on a web app. Screens captured:\n"]
    for s in screens:
        if s.get("error"):
            out.append(f"- [{s.get('reaches') or s['label']}] FAILED ({s['did']}): {s['error']}"); continue
        out.append(f"### {s['title']} — {s.get('reaches') or s['label']}  [screenshot: {s['screenshot']}]")
        if s["headings"]: out.append("headings: " + " | ".join(s["headings"]))
        out.append("text: " + s["text"][:360])
    out.append(f"\nThe user wants to demo: {GOAL}.\nProduce app_model, proposed_intent "
               "(goal/audience/tone/focus), screens (name+route+screenshot for each), warnings.")
    return "\n".join(out)


async def plan_call(dump):
    be = PydanticAIBackend(default_model="openrouter:deepseek/deepseek-chat-v3.1",
                           allowed_roots=[P("/tmp")], cwd=P("/tmp"))
    class C: event_emitter = None
    t = time.monotonic()
    r = await be.run_structured(C(), PLAN_TPL.format(url=START, dump=dump, goal=GOAL),
                                "phase2-plan", output_type=ExplorePlan)
    print(f"PLAN ({time.monotonic()-t:.0f}s): setup={len(r.output.setup)} steps, {len(r.output.paths)} paths")
    for st in r.output.setup: print(f"  [setup] {st.action} {st.target!r} {st.value!r}")
    for pth in r.output.paths: print(f"  path → {pth.reaches}: " + " → ".join(f"{s.action} {s.target!r}" for s in pth.steps))
    return r.output


async def interp_call(screens):
    be = PydanticAIBackend(default_model="openrouter:deepseek/deepseek-chat-v3.1",
                           allowed_roots=[P("/tmp")], cwd=P("/tmp"))
    class C: event_emitter = None
    t = time.monotonic()
    r = await be.run_structured(C(), interpret_prompt(screens), "phase2-interp", output_type=ExplorePayload)
    print(f"INTERPRET ({time.monotonic()-t:.0f}s)")
    return r.output.model_dump()


t0 = time.monotonic()
with sync_playwright() as _pw:
    _b = _pw.chromium.launch(); _pg = _b.new_page()
    _pg.goto(START, wait_until="domcontentloaded"); _pg.wait_for_selector("body")
    DUMP = "\n".join(f"- {x['tag']} {x['text']!r}" for x in interactive_dump(_pg)); _b.close()

plan = asyncio.run(plan_call(DUMP))
te = time.monotonic()
screens, failures = run_plan(plan)
print(f"\nEXEC ({time.monotonic()-te:.0f}s): {len(screens)} screens, {failures} failures")
for s in screens:
    print("  ", ("FAIL " if s.get("error") else "ok   "), s.get("reaches"), "|", s.get("error") or (s.get("did") or "")[:70])
payload = asyncio.run(interp_call(screens))
print("TOTAL WALLCLOCK: %.0fs" % (time.monotonic()-t0))
print("validate:", _validate_payload(payload, EXP) or "OK")
prop = _normalized_proposal(payload)
print("app_model:", payload["app_model"][:200])
print("goal:", prop["goal"])
print("screens:", [s.get("name") for s in payload.get("screens", [])])
