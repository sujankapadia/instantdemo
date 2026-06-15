# Agent SDK Portability — Moving Off the Claude Agent SDK

**Status: research, not a decision.** Captures a 2026 survey of what
it would take to port InstantDemo's per-phase agent loop off the
Claude Agent SDK to run non-Anthropic models, while keeping the
pipeline's functionality. Findings were web-researched and
adversarially verified (25 claims, 0 refuted); the cross-model
quality and cost-tracking questions are explicitly flagged as
prototype-only.

## Why this exists

Two standing concerns motivated it: (1) the cost of full pipeline
runs, and (2) not wanting to be permanently locked to
Claude/Anthropic if a comparable-but-cheaper model appears. The
Claude Agent SDK has **no supported path to non-Anthropic models**
(only Claude-on-other-clouds via Bedrock/Vertex/Azure, or an
unofficial LiteLLM proxy that breaks the structured-output
semantics this pipeline depends on — see the earlier SDK lock-in
finding). So the real question: which agent SDK could we port to
that supports other models AND retains the workflow? At its core any
agent is a loop + tool calls, so the workflow should largely
transfer.

## The port surface is small

Orchestration BETWEEN phases is already plain deterministic Python
(`phases/` runners control sequence, validation, merge). The agent
SDK is used only WITHIN each phase. So a port swaps just the
per-phase agent loop (`ClaudeSDKClient` + the message-consuming
loop) and re-provides the built-in tools the agent uses
(Bash/Read/Glob/Grep).

## Recommendation

**Prototype Pydantic AI first; AWS Strands second.**

Pydantic AI is the best fit precisely because of the features this
pipeline leans on. The mapping to today's Claude Agent SDK usage is
almost one-to-one:

| InstantDemo need (Claude Agent SDK) | Pydantic AI equivalent (verified) |
|---|---|
| PreToolUse hook (intercept tool calls) | **WrapperToolset** — wraps/intercepts before execution |
| Per-phase tool allowlist | **FilteredToolset** — allowlist filtering; dynamic gating via ApprovalRequiredToolset |
| `run_structured_query` (fenced JSON + 1 corrective retry) | **native `output_type`** (Pydantic models) + **`output_validator` with retries**; three output modes |
| Multi-model | **native** support for ~all major providers (not just a proxy) |
| Tools | `@agent.tool` |

The structured-output story is the standout — it is *cleaner* than
the current fenced-JSON-with-corrective-retry, because
validation+retry is native to the framework instead of hand-rolled.
Given how hard phases 2–4 lean on validated JSON, that is the single
biggest reason it is the top pick.

**AWS Strands** is the close second — native
Bedrock/Anthropic/OpenAI/Gemini, a `BeforeToolCallEvent` hook for
interception, native Pydantic structured output. Choose it over
Pydantic AI only if going AWS/Bedrock-centric.

The others, briefly:
- **LangGraph / LangChain 1.0** — capable (`wrap_tool_call`
  middleware for interception; dynamic tool restriction) but heavier
  boilerplate for no gain here.
- **OpenAI Agents SDK** — weakest fit: OpenAI-only natively, other
  providers only via a LiteLLM shim, and it explicitly warns that
  non-OpenAI providers emit invalid JSON — exactly this pipeline's
  failure mode.
- **LiteLLM** — the universal fallback (100+ providers,
  OpenAI-compatible) but a routing layer, not an agent loop.

## Two things that matter more than the SDK choice

1. **None of them ship Bash/Read/Glob/Grep.** Reimplement those four
   (~50 lines each: subprocess, file read, glob, grep). Small, but
   real — and it is where the filesystem-jail enforcement would
   re-live (inside the WrapperToolset / before-tool hook).

2. **The load-bearing gotcha (verified 3-0): "structured/JSON output
   is not reliable across all models."** The SDK port is the easy,
   bounded part. The actual risk is whether a cheap non-Claude model
   holds up on the hardest tasks — writing correct Playwright scripts
   in a Bash loop, and emitting clean validated JSON every phase.
   That is model quality, not SDK capability, and it is exactly where
   Claude is strong. Docs could not settle it; **open-model quality
   vs Claude, and per-call cost tracking, are prototype-only
   questions.**

## What this means for the decision

It de-risks the lock-in worry concretely: there is a clean,
framework-supported escape hatch (Pydantic AI), and the port surface
is genuinely small — between-phase orchestration stays as-is; swap
the per-phase loop and re-provide four tools. "We could move off
Claude" is now a known, bounded option, not a scary unknown.

It does not change the sequencing. The cheapest cost lever is still
**#81 (per-phase Claude model pinning)** — zero port, zero risk,
available now. The Pydantic AI port only pays off if a specific
cheaper non-Claude model proves *comparable on the agentic +
structured work* — an open question best settled by a one-phase
spike (port just Phase 3, the most mechanical, to Pydantic AI + one
candidate model, and measure JSON-validity rate, Playwright-script
success, and cost), not a full migration.

**So if/when model cost becomes a real pressure: #81 first; then a
single-phase Pydantic AI + cheap-model spike to test the
"comparable" assumption before committing.**

## Spike results (2026-06-15)

A standalone half-day spike (`scripts/explore/pydantic_ai_spike.py`,
throwaway — does not touch the pipeline) reproduced one
Phase-4-shaped task with Pydantic AI 1.107 against the live Evernote
fixture: the agent writes and runs a Playwright verification script
through a jailed bash tool and returns findings that validate against
a schema.

**The SDK-port half is validated with running code** — the 1:1
mapping from the table above is real, not just documented:
- `WrapperToolset.call_tool` intercepts every tool call before
  execution = the PreToolUse-hook + filesystem-jail analog. ✓
- `FilteredToolset(wrapped, filter_func)` = the per-phase allowlist. ✓
- `output_type` (a Pydantic model) + an `@agent.output_validator`
  that raises `ModelRetry` = structured output with corrective
  retry — cleaner than the hand-rolled fenced-JSON path. ✓
- a `FunctionToolset` `bash` tool drove real Playwright; `result.usage`
  gives per-run token counts. ✓

**Claude baseline (`anthropic:claude-sonnet-4-6`), 5/5 runs:**
script-success 5/5, json-valid 5/5, ~2450 input / ~490 output tokens,
1 tool call, ~11s each. Rock-solid — the sanity check on the harness.

## Model comparison — verify vs. repair (OpenRouter, 2026-06-15)

Candidates were run through OpenRouter against two scenes: **good**
(verify-only — the correct selector handed in; the floor of the
difficulty curve) and **broken** (a stale selector that doesn't
exist — the model must DETECT the failure, inspect the live DOM, find
the real control, repair, and complete; the Phase-4 Level-1 repair
skill, where the Claude/cheap boundary should show).

**Verify (good scene), 10 runs each:**

| Model | success | json | tools/run | ~speed | ~¢/run* |
|---|---|---|---|---|---|
| Claude Sonnet 4.6 (baseline, 5 runs) | 5/5 | 5/5 | 1 | ~11s | ~1.5¢ |
| Gemini 3.1 Flash-Lite | 10/10 | 10/10 | 1 | ~5s | ~0.02¢ |
| Qwen3-Coder 30B | 10/10 | 10/10 | 2–3 | ~8s | ~0.02¢ |
| Qwen3-235B-A22B | 10/10 | 10/10 | 1 (one 6× spiral) | ~11s | ~0.015¢ |
| DeepSeek-v4-Flash | DNF — no first response in 90s (reasoning-tier latency) |
| gpt-5-nano | DNF — no first response in 90s (reasoning-tier latency) |

**Repair (broken scene), 5 runs each:**

| Model | recovered | tools/run | tokens in/out | notes |
|---|---|---|---|---|
| Claude Sonnet 4.6 (1 run) | 1/1 | 5 | ~25k / 3k | reference; repair is ~10× the verify cost |
| Gemini 3.1 Flash-Lite | **5/5** | 2–5 | ~4–18k / ~1k | clean recovery every run — found `#source-select` after the dead selector |
| Qwen3-Coder 30B | 4/12 across two batches; recovers when it connects but laboriously (8 tools, 72–90s, ~26k tok — brushing the timeout) | | | + ~half the runs died on provider `Connection error` |
| Qwen3-235B-A22B | 1/10 — provider too flaky to judge | | | nearly all runs died on `Connection error`; the one clean run recovered |

\*observed tokens × live OpenRouter price; Claude at standard Sonnet
rates. Repair scenes cost ~10× the tokens of verify.

**Findings:**
1. **Cheap models clear this task — including repair.** Gemini 3.1
   Flash-Lite went 10/10 verify AND 5/5 repair at ~75× lower cost than
   Claude, matching Claude's iterate-to-fix behavior. The repair pass
   is the surprise — it's the hard Phase-4 skill and the cheap model
   held up. Gemini Flash-Lite is the clear candidate to beat.
2. **Latency is a real disqualifier.** The two reasoning-tier minis
   (DeepSeek-v4-Flash, gpt-5-nano) never returned a first response in
   90s — unusable for an interactive loop regardless of quality.
3. **OpenRouter provider reliability varies by model.** The Qwen
   models' backing providers dropped connections repeatedly during
   testing (Gemini's was rock-solid). An operational signal, not a
   capability verdict — but it matters for a production tool, and it
   left Qwen's repair capability only partially measured (Qwen-Coder
   *can* repair, but heavily).

## Narration A/B — the Phase-2 prose test (2026-06-15)

A second throwaway harness (`scripts/explore/narration_ab.py`) isolates
the opposite of the scripting test: prose quality. It feeds each model
the REAL phase2 narration rules + the app one-pager + one chapter's
already-planned scenes (narration hidden) and asks only for the
narration, printed against the Claude-pipeline original. Two chapters,
one generation per model — a small qualitative sample, a read not a
metric. Findings:

- **Search chapter — Claude clearly better.** Gemini drifted to
  documentation-voice ("The app finds notes containing the term in the
  body text") with tells ("appear instantly", "Start by typing");
  Claude read like a person.
- **Privacy chapter — a wash.** Gemini's "No cloud sync. No servers.
  Just your files." was genuinely punchy; on the payoff line BOTH
  Claude-now and Gemini went procedural and missed the original's
  landing ("Your notes left Evernote. They didn't leave you.").
- **The original beat BOTH isolated calls — from pipeline context, not
  raw model power.** The original had the whole-film arc, the intent
  emphasis, the observed counts (Phase 1/3), and the continuity pass;
  the isolated harness gave neither model those. So the architecture
  does much of the narration-quality work, and it helps whichever model
  runs it.

Net of the isolated test: the prose gap looked **modest** — which
turned out to be misleading (see below). The isolated harness handed
each model the scene structure and didn't require grounding to observed
data, hiding the two things a small model actually fails at.

## Full Phase-2 A/B — the decisive test (2026-06-15)

A third harness (`scripts/explore/phase2_ab.py`) reproduces the WHOLE
Phase-2 flow — outline → per-chapter narration → continuity pass — on
each model, using the real prompts and the real Evernote inputs
(intent.json, phase1.md, product-context.md). This exercises the chapter
ARC and the continuity pass, which the isolated test couldn't. It
**reverses** the soft read, and not on prose taste — on correctness:

- **Gemini hallucinated the core facts, consistently.** Run 1 narrated
  "14,285 Notes"; run 2 "4,287 notes" — the real count is **500**. It
  invented search examples ("recipe"/"basil pesto"; "Project Alpha")
  instead of the actual 'REDACTED-TERM'/'kubernetes' in the Phase-1 data, and
  referenced the **import button that intent.excludes lists**. Two for
  two: the small model defaults to plausible placeholders instead of
  grounding to provided data — disqualifying for a demo tool, where the
  narration would confidently describe things that aren't true.
- **Gemini's continuity pass is non-functional.** It returned 0 rewrites
  while its explanation *claimed* it "removed repetitive openers and
  synthesized redundant statements" — describing fixes it never made,
  and missing real cross-chapter repetition.
- **Gemini under-covered** the comprehensive brief (4 chapters vs 7;
  dropped the export-count verification beat).
- **Claude did all three right:** grounded every specific to the
  observed values (500, REDACTED-TERM→50, kubernetes→34, 100/file × 5), built
  a strong payoff-first 7-chapter arc, and its continuity pass caught
  **4 genuine cross-chapter problems** with precise reasoning (duplicate
  opener, a line repeated across a chapter break, a premature privacy
  claim, a duplicated closing detail).

Lesson: the isolated narration test was a trap — it understated the gap
by removing grounding and whole-document judgment, the exact things
small models fail at. The full pipeline is the honest test. But the
boundary turned out to be a **capability TIER**, not "Claude vs. the
rest" (see the mid-tier sweep below): Flash-Lite is simply too weak for
Phase 2.

## Mid-tier sweep — Phase 2 doesn't actually require Claude (2026-06-15)

The full Phase-2 A/B run on cheaper-but-capable models (the question:
is there a model comparable to Claude, cheaper, without the
cold-start/stall the reasoning-minis showed?). Grounding ladder, by
tier:

| Model | in/out $/M | grounds the facts? | continuity pass | stall? |
|---|---|---|---|---|
| `gemini-3.1-flash-lite` | ~0.10/0.40 | NO — fabricates the count (14,285 / 4,287; real 500) | fake (0 rewrites, claims fixes) | no |
| `gemini-2.5-flash` | 0.30/2.50 | partial — stops fabricating, goes vague/generic ("Meeting") | — | no |
| `gemini-3-flash-preview` | 0.50/3.00 | mostly — uses 500 + REDACTED-TERM/kubernetes, but kubernetes "3" not 34, invents a PDF | fake (0 rewrites, claims fixes) | no |
| **`deepseek-chat-v3.1`** | **0.21/0.79** | **yes — 500, REDACTED-TERM, kubernetes→34 (exact)** | **WORKS — 6 real cross-chapter rewrites** | **no (non-reasoning V3)** |
| Claude Sonnet 4.6 | ~3/15 | yes (reference) | works (4 rewrites) | no |

**The standout: `deepseek/deepseek-chat-v3.1`.** It is the only
cheap+fast model that cleared BOTH bars Flash-Lite failed — it grounded
to the exact observed values (including kubernetes→34, which gemini-3-flash
got wrong) AND its continuity pass actually found and fixed 6
cross-chapter issues (the Gemini family uniformly returned 0 rewrites
while *claiming* fixes — a non-functional whole-document pass). It's
~14× cheaper than Claude and didn't stall (the non-reasoning V3, unlike
its v4-flash reasoning sibling that hung at 90s).

So **Phase 2 doesn't require Claude — it requires a capable model, and
there are cheap ones.** The earlier "stays on Claude" was a flash-lite
artifact.

**Reliability — confirmed (6/6).** A follow-up batch ran the full
Phase-2 flow on `deepseek-chat-v3.1` six times (~48 model calls): zero
connection drops, the 500 count grounded every run, the continuity pass
functional every run (7/8/8/6/11 rewrites, plus one legitimate 0 =
"reads fine"). The earlier DeepSeek flakiness was the *reasoning*
v4-flash variant, not V3-chat. Still owed: a blind PROSE read (grounding
+ continuity are correctness bars, not narrative elegance); one minor
embellishment seen (an invented note title).

## Phase-1 A/B — explore + propose intent (2026-06-15)

Phase 1 is the hybrid: drive the live app (Playwright via bash) to
explore it, THEN propose a demo intent. Harness:
`scripts/explore/phase1_ab.py`. Result — depth scales with capability,
but NONE hallucinate features (unlike Phase 2):

| Model | tool calls | intent depth |
|---|---|---|
| Claude Sonnet 4.6 | **38** | exhaustive — *discovered* counts by experimenting ('REDACTED-TERM'→22, 'REDACTED-TERM'→6, 'REDACTED-TERM'→1), found attachments/sources/API endpoints/250ms debounce, 6 sharp warnings |
| `deepseek-chat-v3.1` | 7 | solid — grounded (500 across 5 files), found attachments + sources, good warnings (incl. "test data may be confidential") |
| `gemini-3.1-flash-lite` | 5 | shallow but grounded — note list + search only; MISSED attachments + sources; generic |

Key cross-phase insight: **the splitter is precision, not the task.**
Phase-1 intent is high-level/qualitative ("search exists") — cheap
models ground it fine, just less thoroughly (a thinner exploration →
fewer features surfaced → a less comprehensive demo, not a wrong one).
Phase-2 needs *precise* grounding (exact counts) — which is exactly
where flash-lite fabricates and a capable model (DeepSeek) is required.
So Phase 1 *tolerates* cheap models with a thoroughness cost; Phase 2
*fails* on the weak ones.

**Recommendation (refines #81) — now evidence-backed end to end:**
per-phase model pinning, not an all-or-nothing swap.
- **Pin the mechanical phases** (3 selectors, the drift check, plausibly
  4's verify/repair) to Gemini 3.1 Flash-Lite — verify AND repair both
  cleared at ~75× lower cost.
- **Phase 2 (outline + narration + continuity) needs a CAPABLE model —
  but not Claude.** Flash-Lite fails (fabricates facts, fake
  continuity); `deepseek-chat-v3.1` cleared grounding + continuity, 6/6
  reliable, at ~14× under Claude. (Blind prose read still owed.)
- **Avoid reasoning-tier minis** for interactive phases (latency:
  deepseek-v4-flash and gpt-5-nano never returned in 90s).
- **Pin to a known-good OpenRouter provider** (or a fallback) given the
  reliability spread.

### Final per-phase pinning map (evidence-backed)

| Phase | Skill | Recommended tier | Evidence |
|---|---|---|---|
| 1 Understand | explore + intent | mid (DeepSeek-V3) for depth; Flash-Lite OK for a quick demo | grounds at every tier; depth scales (38/7/5 tool calls) |
| 2 Plan | grounding + continuity | **mid (DeepSeek-V3)** | flash-lite fabricates; DeepSeek 6/6 clean |
| 3 Inspect | source → selectors | **cheap (Flash-Lite)** | mechanical; verify proxy 10/10 (direct test still owed) |
| 4 Rehearse | drive + repair | **cheap (Flash-Lite)** | verify 10/10, repair 5/5 |
| 5 Build | projection | n/a — deterministic | no model |
| 6 Render | drift check | cheap | trivial one-shot |

Net: the whole pipeline can plausibly run **off Claude** on two cheap
tiers — Gemini Flash-Lite for the mechanical phases (~75× cheaper),
DeepSeek-V3-chat for the judgment phases (1–2, ~14× cheaper) — with
Claude as a quality fallback. Remaining before committing: a direct
Phase-3 test, blind prose reads of the DeepSeek judgment output, and the
actual port of `phases/` to Pydantic AI (bounded — the SDK mechanics are
proven).

## Sources

Primary docs and verified comparisons (2026):
- Pydantic AI — https://ai.pydantic.dev/ , /toolsets/ , /output/
- AWS Strands — https://github.com/strands-agents/sdk-python ,
  https://strandsagents.com/docs/user-guide/concepts/model-providers/
- OpenAI Agents SDK — https://openai.github.io/openai-agents-python/models/ ,
  /guardrails/
- LangChain middleware — https://docs.langchain.com/oss/python/langchain/middleware/custom
- LiteLLM providers — https://docs.litellm.ai/docs/providers
