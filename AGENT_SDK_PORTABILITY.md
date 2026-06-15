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

## Sources

Primary docs and verified comparisons (2026):
- Pydantic AI — https://ai.pydantic.dev/ , /toolsets/ , /output/
- AWS Strands — https://github.com/strands-agents/sdk-python ,
  https://strandsagents.com/docs/user-guide/concepts/model-providers/
- OpenAI Agents SDK — https://openai.github.io/openai-agents-python/models/ ,
  /guardrails/
- LangChain middleware — https://docs.langchain.com/oss/python/langchain/middleware/custom
- LiteLLM providers — https://docs.litellm.ai/docs/providers
