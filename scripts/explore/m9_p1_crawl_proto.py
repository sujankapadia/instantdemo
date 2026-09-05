"""Prototype: runner-driven Phase 1 (deterministic crawl -> batch interpret).

Standalone, does NOT touch the real pipeline. Compares against the
agent-driven Phase 1 (which found 2-15 screens in 200s-timeout).

Crawl: sync Playwright (as render.py uses) BFS over same-origin a[href]
links from the start URL, screenshot + extract title/headings/text per
screen. Then ONE batched DeepSeek call interprets the crawl into the
existing ExplorePayload (app_model / proposed_intent / screens / warnings).
"""
import asyncio, time
from pathlib import Path
from urllib.parse import urljoin, urlparse
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env")
from playwright.sync_api import sync_playwright
from instantdemo.agent_backend import PydanticAIBackend
from instantdemo.phases.analyze import ExplorePayload, _validate_payload, _normalized_proposal

START = "http://localhost:8001"
MAX_SCREENS = 12
EXP = Path("/tmp/m9-p1-proto/exploration"); EXP.mkdir(parents=True, exist_ok=True)
for p in EXP.glob("*.png"): p.unlink()


def same_origin(u, base):
    return urlparse(u).netloc == urlparse(base).netloc


def crawl():
    """Deterministic BFS crawl. Returns list of screen dicts."""
    screens, seen = [], set()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        queue = [START]
        while queue and len(screens) < MAX_SCREENS:
            url = queue.pop(0)
            norm = url.rstrip("/")
            if norm in seen:
                continue
            seen.add(norm)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
                page.wait_for_selector("body", timeout=5000)
            except Exception as e:
                screens.append({"url": url, "error": str(e)[:80]})
                continue
            idx = len(screens) + 1
            shot = f"{idx:03d}-{urlparse(url).path.strip('/').replace('/','-') or 'home'}.png"
            try:
                page.screenshot(path=str(EXP / shot), full_page=False)
            except Exception:
                shot = None
            title = page.title()
            headings = page.eval_on_selector_all(
                "h1,h2,h3", "els => els.map(e => e.innerText.trim()).filter(Boolean).slice(0,8)")
            text = page.eval_on_selector_all(
                "body", "els => els[0] ? els[0].innerText.slice(0,600) : ''")
            text = (text[0] if isinstance(text, list) else text) or ""
            # collect same-origin nav links to enqueue
            hrefs = page.eval_on_selector_all(
                "a[href]", "els => els.map(e => e.getAttribute('href'))")
            for h in hrefs:
                if not h or h.startswith(("#", "javascript:", "mailto:")):
                    continue
                full = urljoin(url, h)
                if same_origin(full, START) and full.rstrip("/") not in seen:
                    queue.append(full)
            screens.append({"url": url, "screenshot": shot, "title": title,
                            "headings": headings, "text": text})
        browser.close()
    return screens


def build_prompt(screens):
    lines = ["I crawled a running web app and captured these screens. "
             "Interpret them and propose a demo.\n"]
    for s in screens:
        if s.get("error"):
            lines.append(f"- {s['url']} — FAILED: {s['error']}")
            continue
        lines.append(f"### {s['title']}  ({s['url']})  [screenshot: {s['screenshot']}]")
        if s["headings"]:
            lines.append("headings: " + " | ".join(s["headings"]))
        lines.append("text: " + s["text"].replace("\n", " ")[:400])
    lines.append(
        "\nThe user wants to demo: Show how to browse and search imported notes.\n"
        "Produce app_model (what the app is/does), proposed_intent "
        "(goal/audience/tone/focus), screens (name+route+screenshot for each "
        "above), and warnings.")
    return "\n".join(lines)


async def interpret(screens, t0, t_crawl):
    prompt = build_prompt(screens)
    be = PydanticAIBackend(default_model="openrouter:deepseek/deepseek-chat-v3.1",
                           allowed_roots=[Path("/tmp")], cwd=Path("/tmp"))
    class C: event_emitter = None
    t1 = time.monotonic()
    r = await be.run_structured(C(), prompt, "phase2-proto", output_type=ExplorePayload)
    t_model = time.monotonic() - t1
    payload = r.output.model_dump()
    print(f"\nMODEL: interpreted in {t_model:.0f}s")
    print("TOTAL WALLCLOCK: %.0fs" % (time.monotonic() - t0))
    print("validate:", _validate_payload(payload, EXP) or "OK")
    prop = _normalized_proposal(payload)
    print("\napp_model:", payload["app_model"][:300])
    print("\nproposed goal:", prop["goal"])
    print("focus:", prop["focus"], "| audience:", prop["audience"])
    print("screens:", [s.get("name") for s in payload.get("screens", [])])
    print("warnings:", payload.get("warnings"))


# crawl runs OUTSIDE the asyncio loop (sync Playwright can't run inside it)
t0 = time.monotonic()
screens = crawl()
t_crawl = time.monotonic() - t0
print(f"CRAWL: {len(screens)} screens in {t_crawl:.0f}s")
for s in screens:
    print("  ", s.get("title") or s.get("error"), "->", s.get("url"))
asyncio.run(interpret(screens, t0, t_crawl))
