# GLM 5.2 — Evaluation for the InstantDemo Agent Pipeline

**Research date:** 2026-06-22 · **Context:** the M9 port (running the
per-phase agent loop on non-Anthropic models — see
`AGENT_SDK_PORTABILITY.md`). This doc captures the GLM 5.2 findings:
availability, pricing, caching, Anthropic-API compatibility, data
residency, and the wiring into our Pydantic AI backend.

**Conventions:** **[CONFIRMED]** = read on an official/primary source
(z.ai docs, HuggingFace, OpenRouter API). **[INFERRED]** = analysis or
cross-derived. **Prices and availability are time-sensitive** (model
landscape moves monthly) — re-verify before relying on any number.

---

## TL;DR / decision summary

- **GLM 5.2 is z.ai's (Zhipu AI's) current flagship**, released ~June
  13–17 2026, superseding GLM 4.6. **[CONFIRMED]**
- It is **fully open-weight (MIT, on HuggingFace `zai-org/GLM-5.2`,
  ~753B-param MoE, 1M context).** So you are **not** locked to z.ai's
  endpoint — US providers host it. **[CONFIRMED]**
- **z.ai-direct runs inference in Singapore (not mainland China)** and
  claims zero retention — but the parent (Zhipu) is a **PRC company on
  the US Commerce Entity List**. Data still leaves the US. **[CONFIRMED]**
- **You can run GLM 5.2 on a US company *with* caching** (e.g. DeepInfra
  via OpenRouter) — US-hosting and caching are **NOT** mutually
  exclusive. **[CONFIRMED]**
- The **caching machinery we built for Claude (`anthropic_cache` /
  `cache_control`) does NOT cleanly transfer** to z.ai's Anthropic
  endpoint. Use the **OpenAI-compatible path** (the same `OpenAIChatModel`
  route our harness already uses for OpenRouter), where caching is
  automatic and observable via `prompt_tokens_details.cached_tokens`.
- **Recommendation:** if pursuing GLM 5.2, pin **DeepInfra** via OpenRouter
  (`provider: {only: ["deepinfra"], allow_fallbacks: false}`) — US
  company, cheapest, with caching — and keep the MIT weights as a
  self-host escape hatch if compliance tightens. Probe caching empirically
  before trusting it.

---

## 1. Availability & API

| | Detail |
|---|---|
| Vendor | Z.ai / Zhipu AI (PRC; international brand "Z.ai") **[CONFIRMED]** |
| Direct base URL (intl) | `https://api.z.ai/api/paas/v4/` (OpenAI-SDK-compatible; `…/chat/completions`) **[CONFIRMED]** |
| Model id | `glm-5.2` (1M-context variant `glm-5.2[1m]`) **[CONFIRMED]** |
| China-domestic route | `open.bigmodel.cn/api/paas/v4/` — separate endpoint; serving `glm-5.2` there is **[INFERRED]** |
| OpenRouter id | `z-ai/glm-5.2` — **16 providers** (DeepInfra, Fireworks, Together, Novita, AtlasCloud, Cloudflare, SiliconFlow, Z.AI, …) **[CONFIRMED]** |
| Open weights | `huggingface.co/zai-org/GLM-5.2`, **MIT**, safetensors, ~753B MoE, 1M ctx (code repo Apache-2.0) **[CONFIRMED]** |

Sources: docs.z.ai/guides/llm/glm-5.2, /api-reference/llm/chat-completion;
huggingface.co/zai-org/GLM-5.2; openrouter.ai/z-ai/glm-5.2 (all 2026-06-22).

---

## 2. Pricing (USD per 1M tokens)

**Quantization matters** — OpenRouter's 18 endpoints differ in precision,
and the cheapest are the most compressed. `tag` from the endpoints API:

| Route | Quant | Input | Cached input | Output | Notes |
|---|---|---|---|---|---|
| **DeepInfra** (US co.) | **fp4** | **$1.00** | $0.18 *(listed; **does NOT cache in practice** — §2a)* | **$4.00** | cheapest, but 4-bit **[CONFIRMED]** |
| Novita | fp8 | $1.33 | $0.247 | $4.18 | **[CONFIRMED]** |
| Fireworks (US co.) | full | $1.40 | $0.26 | $4.40 | **[CONFIRMED]** |
| Together (US co.) | full | $1.40 | $0.26 | $4.40 | **[CONFIRMED]** |
| Z.AI (first-party) | fp8 | $1.40 | $0.26 | $4.40 | **[CONFIRMED]** |
| **z.ai-direct PAYG** | $1.40 | $0.26 | $4.40 | Singapore **[CONFIRMED]** |
| OpenRouter (default routing) | $1.00 | (not published) | $4.00 | varies by chosen provider **[CONFIRMED]** |
| Baseten | serves it (SOC2/US positioning); price not published **[CONFIRMED availability]** |
| Amazon Bedrock | carries GLM 5 / GLM 4.7, **not** 5.2 **[CONFIRMED]** |

**For comparison (other models, this branch):**
- DeepSeek-V3.x via OpenRouter ≈ $0.27 / $1.10
- Claude **Opus 4.8**: $5.00 / $25.00, cache-read $0.50 (Fast: $10 / $50)
- Claude **Sonnet 4.6** (what we validated this session): cheaper Claude tier

**Reading it:** GLM 5.2 is mid-priced — pricier than DeepSeek, far cheaper
than Opus. Output ($4/M) is its expensive leg. Caching mainly helps the
input/prefix leg (the agent loop's re-sent context).

Not serving GLM at all (as of 2026-06-22): SambaNova, Groq, Azure AI
Foundry, Vertex AI **[CONFIRMED-by-absence]**. Cerebras serves GLM-4.6/4.7
but 5.2 unconfirmed.

---

## 2a. MEASURED — caching probe results (2026-06-22) **[CONFIRMED empirically]**

We ran the same probe pattern used to validate the Claude caching fix.
**Caching works on GLM 5.2 via OpenRouter — with one important trap.**

| Probe | Result |
|---|---|
| Cross-call (2 calls, same session, default routing) | `cache_read = 2,368` on call 2 — **✓ caches** |
| Multi-turn tool loop (8-link Read chain, default routing) | 15 turns, input 93,822, **`cache_read = 81,899` (87%)**, `cache_write = 0` — **✓ caches the growing loop** |
| Same cross-call probe **pinned to DeepInfra** | `cache_read = 0` on both calls — **✗ does NOT cache** |
| Same loop pinned to Together | HTTP 429 rate-limited upstream — unverified |

**Trap:** DeepInfra advertises a $0.18/M cache-read price on OpenRouter but
returned **zero cache reads** in practice. The §6 recommendation to pin
DeepInfra (written before this probe) is **superseded** — use default
routing or a provider verified to cache. Also note DeepInfra serves **fp4**
(4-bit quantized), a quality risk for agentic work.

**GLM charges nothing for cache writes** (`cache_write = 0`), vs Claude's
$3.75/M — a real structural advantage for short-lived sessions.

### Head-to-head on an identical task (8-link Read chain)

| | Turns | Input tokens | Cache read | Actual cost |
|---|---|---|---|---|
| Claude Sonnet 4.6 | 11 | 31,568 | 28,221 (89%) | **$0.030** |
| **GLM 5.2** | 15 | 93,822 | 81,899 (87%) | **~$0.022** (est.) |

**The key finding:** GLM 5.2's per-token price is ~4x cheaper, but it burned
**3x more input tokens** on the identical task (more turns, more context per
turn) — so the *actual* saving was only **~25%**, not 4x. Budget for
**25–50% real savings vs Sonnet**, not the headline multiple, until measured
on a real phase. This is a milder version of the turn-inefficiency we saw
with GLM-4.6.

*Telemetry note:* `total_cost_usd` reports **$0.0000** for
`openrouter:z-ai/glm-5.2` — genai-prices doesn't price it. Costs above are
computed from token counts at $0.77 / $2.42 / $0.143 per M. Any GLM cost
telemetry in the pipeline will read zero until this is handled.

### Live pricing drift
Headline pricing **moved during this evaluation** (first pull $1.00/$4.00;
second pull $0.77/$2.42). Treat every price in this doc as a snapshot and
re-query `openrouter.ai/api/v1/models` before relying on it.

---

## 3. Caching

### z.ai native ("Context Caching")
- Automatic / implicit (no cache breakpoints to declare). **[CONFIRMED —
  docs.z.ai/guides/capabilities/cache]**
- Cache hits report via the **OpenAI-style** field
  `usage.prompt_tokens_details.cached_tokens` — **NOT** Anthropic's
  `cache_read_input_tokens`.
- Docs describe matching as content "identical or **highly similar**" to
  prior requests (similarity-framed). Whether it is strict growing-prefix
  *incremental* caching (what our tool loop needs) is **[INFERRED]**, not
  guaranteed in those words. There is a TTL (duration unpublished).

### US providers (DeepInfra / Fireworks / Together)
- All expose cache-read pricing on OpenRouter (DeepInfra $0.18/M cheapest,
  most $0.26/M). So **US-hosting and caching coexist.** **[CONFIRMED]**
- This caching is the provider's own (OpenAI-style), applied through the
  OpenAI-compatible API. **Verify empirically** that hits register — our
  earlier DeepSeek-via-OpenRouter caching never showed clearly in cost
  telemetry. **[INFERRED — needs a probe]**

### The Anthropic-path caching caveat (important)
- z.ai's caching is documented **only on the native `/paas/v4` path**.
- **No z.ai doc states the Anthropic endpoint honors `cache_control`
  markers or returns Anthropic cache-usage fields.** Community
  Claude-Code-on-GLM reports confirm usage does **not** come back in
  Anthropic format (statusline cache bars break). **[CONFIRMED via
  community repos; adversarially verified → REFUTED on the strong form]**
- **Conclusion:** treat Anthropic-style `cache_control` as a **no-op** on
  z.ai's Anthropic endpoint. The `anthropic_cache` machinery we tuned for
  Claude will NOT produce observable cache hits there.

---

## 4. Anthropic-API compatibility & Pydantic AI wiring

z.ai **does** expose an Anthropic-compatible `/v1/messages` endpoint:
- Base URL: `https://api.z.ai/api/anthropic` (SDK appends `/v1/messages`)
- Auth: `ANTHROPIC_AUTH_TOKEN=<z.ai key>` → sent as `Authorization: Bearer`
  (**NOT** `x-api-key`) — the #1 wiring trap.
- z.ai maps requested Claude model names (Sonnet/Opus) → GLM internally.
- The z.ai **Coding Plan** subscription *requires* this endpoint.

**But** (see §3) caching doesn't demonstrably work on this path. So the
Anthropic route buys easy drop-in reuse of our code at the cost of an
**unverified / likely-silent** caching benefit.

### Two wiring options

**Option A — native OpenAI-compatible path (recommended for caching).**
Same `OpenAIChatModel` route our `resolve_model` already uses for
OpenRouter. Caching is automatic and observable via `cached_tokens`. Add a
`zai:` spec → `OpenAIChatModel("glm-5.2", provider=OpenAIProvider(
base_url="https://api.z.ai/api/paas/v4/", api_key=ZAI_KEY))`. We lose
explicit breakpoint control, but z.ai handles caching server-side.

**Option B — Anthropic-compatible path (drop-in, caching unverified).**
```python
from anthropic import AsyncAnthropic
from pydantic_ai.models.anthropic import AnthropicModel, AnthropicModelSettings
from pydantic_ai.providers.anthropic import AnthropicProvider

client = AsyncAnthropic(
    auth_token="<ZAI_API_KEY>",              # -> Authorization: Bearer (NOT api_key)
    base_url="https://api.z.ai/api/anthropic",
)
model = AnthropicModel(
    "claude-sonnet-4-5",                     # z.ai maps Sonnet/Opus -> GLM
    provider=AnthropicProvider(anthropic_client=client),
    settings=AnthropicModelSettings(
        anthropic_cache_messages="1h",       # per-block (gateway-safe), NOT anthropic_cache
        anthropic_cache_instructions=True,
        anthropic_cache_tool_definitions=True,
    ),
)
```
Use `anthropic_cache_messages` (per-block) — pydantic-ai flags it as the
variant for "Anthropic-compatible gateways that don't support top-level
automatic caching." Gotchas: the `auth_token` header; `AnthropicModel`
injects default `anthropic-beta` headers some non-Anthropic backends
reject (pydantic-ai #2543) — may need stripping.

**The pydantic-ai side is ready either way:** `AnthropicProvider` accepts
`base_url`/`anthropic_client`; `OpenAIChatModel` accepts a custom
`base_url`. Only `resolve_model`/`_cache_settings` need a small `zai:`
branch.

---

## 5. Data residency & hosting (the gating question)

| | z.ai first-party API | US provider (DeepInfra / Fireworks / Together) |
|---|---|---|
| Inference location | **Singapore** **[CONFIRMED]** | US datacenter **[INFERRED — US co.; no region field exposed]** |
| Corporate jurisdiction | PRC parent (Zhipu), on US Entity List **[CONFIRMED]** | US company |
| Data retention | "Zero retention" of API content (self-asserted) **[CONFIRMED]** | per provider policy |
| Caching | $0.26/M cache-read **[CONFIRMED]** | DeepInfra $0.18, most $0.26 **[CONFIRMED]** |
| Best for | lowest friction, first-party | avoiding PRC-jurisdiction egress |

- A Z.ai exec (ChinaTalk): *"We do the inference outside China… all of our
  services are hosted in Singapore… it's a requirement to store the data
  overseas."* Privacy policy: services "generally provided from
  Singapore," API content "processed in real-time… not saved," but
  cross-border-transfer and government-disclosure clauses exist. **[CONFIRMED]**
- **OpenRouter routing:** you can pin a non-China provider
  (`provider: {only: ["deepinfra"], allow_fallbacks: false}`). There is
  **no US region filter** — only EU-in-region (enterprise). So you
  whitelist a US *company* by slug; you do **not** get a contractual
  US-datacenter guarantee. `data_collection: "deny"` is a privacy (not
  geographic) filter. **[CONFIRMED]**
- **Strongest mitigation for strict compliance:** self-host the MIT
  weights on-prem/VPC — prompts and source never leave your network. The
  Entity List restricts US *exports to* Zhipu; it does **not** bar running
  the open weights locally. **[CONFIRMED license; INFERRED recommendation]**

### Compliance flags for a US team
- **Zhipu AI added to the US Commerce Entity List (Jan 16, 2025)** — first
  Chinese LLM company listed. Restricts US *exports to* Zhipu; does **not**
  legally bar a US firm from *using* the API/weights — but a material
  due-diligence/reputational flag. **[CONFIRMED]**
- **PRC National Intelligence Law Art. 7** (orgs "shall support… national
  intelligence") cited by US DNI/DHS as compelling data-sharing —
  enforcement scope legally debated. **[CONFIRMED text; INFERRED reach]**
- **Trend:** DeepSeek banned on US govt devices (federal + 17+ states);
  proposed FAR rule would bar federal acquisition of "PRC models." Scoped
  to government/contractors today, not private commercial — but a
  direction-of-travel signal. **[CONFIRMED]**
- No SOC 2 report confirmed for Z.ai. **[UNVERIFIED]**

### Residency spectrum for sending demo content
- **Cleanest:** Claude (Anthropic, US) — premium price.
- **Middle:** GLM 5.2 or DeepSeek via a **US provider** (US datacenter,
  Chinese-*origin* weights) — cheap, reasonable, self-host escape hatch.
- **Most exposed:** z.ai-direct / DeepSeek-direct (Singapore/China, PRC
  jurisdiction).

---

## 6. Recommendation for the InstantDemo spike

1. **~~Pin DeepInfra~~ — SUPERSEDED by the §2a probe.** DeepInfra returned
   **zero cache reads** despite advertising a cache price, and serves
   **fp4** (4-bit). Use **default routing** (verified to cache, 87% hit
   ratio) or a provider individually verified to cache. For a *quality*
   read, prefer a full-precision provider (Together/Fireworks) over fp4.
   Keep the MIT weights as a self-host option if a customer demands
   provable US residency.
2. **~~Probe caching first~~ — DONE, see §2a.** Caching confirmed working
   on default routing (cross-call and in-loop); expect ~25–50% real cost
   savings vs Sonnet, not the 4x headline.
3. **Don't use the Anthropic path for caching** — `cache_control` is a
   no-op there; if you use it at all, use it only for drop-in convenience,
   not cost.
4. **Weigh residency vs the M9 goal:** GLM 5.2 is mid-priced and Chinese-
   origin. If the driver is pure cost, DeepSeek (or GLM-4.7-flash at
   $0.06/$0.40) is cheaper; if it's quality-near-Claude, GLM's agentic
   benchmarks are strong but our one live GLM-4.6 probe fragmented (see the
   M9 memory note). A real bash-efficiency + caching probe on GLM 5.2 is
   the next concrete step if we pursue it.

---

## Open items to verify before relying on them
- Per-provider **physical US datacenter** location (inferred from
  US-company status; not exposed by OpenRouter).
- GLM 5.2 **release date** (June 2026 secondary sources vs the Feb arXiv
  date on the HF page).
- **Whether OpenRouter→DeepInfra caching actually registers** for
  GLM 5.2 (empirical probe).
- Baseten / Bedrock exact pricing; Z.ai **SOC 2** status.
- z.ai native-path **incremental growing-prefix** caching behavior (docs
  say "similar," not "prefix").

**Primary sources (all accessed 2026-06-22):** docs.z.ai
(/guides/llm/glm-5.2, /api-reference/llm/chat-completion,
/guides/capabilities/cache, /guides/overview/pricing,
/scenario-example/develop-tools/claude, /legal-agreement/privacy-policy);
huggingface.co/zai-org/GLM-5.2; openrouter.ai/z-ai/glm-5.2 + endpoints API;
pydantic-ai docs/models/anthropic.md + issue #2543;
github.com/ankurkakroo2/claude-code-glm-setup; US Commerce Entity List
(Jan 2025).
