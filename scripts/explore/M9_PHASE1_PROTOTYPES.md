# M9 Phase-1 runner-driven exploration prototypes

Research artifacts from the M9 investigation (2026-06-16) into replacing
Phase 1's slow, turn-by-turn agent-driven exploration with a fast
**runner-driven crawl**: the runner drives Playwright deterministically;
the model only PLANS interactions and INTERPRETS results (≈2 bounded
model calls instead of 16+ slow agent turns).

Motivation: on DeepSeek/Qwen3 via OpenRouter, the agent-driven Phase 1
took 200–600s and often timed out (slow output generation over a growing
uncached transcript). These prototypes proved a runner-driven design
completes in ~50–90s, reliably, and generalizes. See the project memory
note `project_m9_pydantic_ai_port` for the full findings.

All are standalone; point them with `M9_URL` / `M9_GOAL` env vars (the
crawl/hybrid default to the evernote app on :8001). They import the real
`agent_backend` + `analyze.ExplorePayload` and call DeepSeek via the .env
key, but DO NOT touch the pipeline.

## The arc (run in this order to follow the reasoning)

| File | Iteration | Result |
|---|---|---|
| `m9_p1_crawl_proto.py` | naive link-crawl | found only 1 screen on a JS SPA — pure `<a href>` crawl is insufficient |
| `m9_p1_hybrid_proto.py` | model plans interactions → runner executes (flat reset-to-baseline, 1 action/reveal) → model interprets | ~47–60s, 0 failures on evernote; great for shallow no-auth apps, can't do auth/depth |
| `m9_p1_paths_proto.py` | adds a **setup/login prefix** (replayed) + **paths**; tuned to SHALLOW reveals | the design winner — handles auth (saucedemo) + breadth; proven across 8 public apps |
| `m9_p1_iter_proto.py` | adds a **bounded 2-round discovery** pass for state-gated UI (TodoMVC's filters appear only after you add an item) | recovers state-gating without the slow turn-by-turn loop; `fill` submits (press Enter) was the key fix |
| `m9_reasoning_probe.py` | latency diagnosis: DeepSeek reasoning on vs off | refuted the "thinking mode" hypothesis (7.1s vs 6.5s) — latency is output-gen + uncached prefill |

## Key conclusions (see memory for detail)
- Generic resolver (Playwright `get_by_role`/`text`/`placeholder`/`label`) —
  no app-specific selectors — generalizes across SPAs, server-rendered,
  catalogs, link-heavy, login-walled, consent-bannered apps.
- Phase 1 wants **breadth + auth, not depth**. Depth (deep workflows) is
  the demo itself, planned by later observe-and-verify phases.
- Backend robustness to fold into the real port: avoid strict `Literal`
  in `output_type` models (DeepSeek intermittently fails them → crash);
  catch `UnexpectedModelBehavior` (retry exhaustion); the jail informs
  rather than raising (already fixed on-branch).
- Open limits: hover-only controls, exact dynamic-item naming, and the
  interpret-call latency variance (the caching/faster-route work trims it).
