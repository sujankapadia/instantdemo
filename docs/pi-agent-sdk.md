# Pi Agent SDK

Research notes on Pi — the agent framework powering OpenClaw.

## What Pi Is

Pi is a TypeScript agent toolkit created by Mario Zechner (badlogic). It's a layered monorepo of npm packages that build on each other:

| Package | Purpose |
|---|---|
| `@mariozechner/pi-ai` | Unified LLM API — streaming, tool calling, multi-provider support |
| `@mariozechner/pi-agent-core` | Agent loop, tool execution, event system |
| `@mariozechner/pi-coding-agent` | Full coding agent with built-in tools, session persistence, extensibility |
| `@mariozechner/pi-tui` | Terminal UI library for CLI interfaces |

The philosophy is minimal and opinionated: by default the model gets four tools (read, write, edit, bash) and figures out the rest. Additional capabilities come through skills, extensions, and prompt templates.

**GitHub**: https://github.com/badlogic/pi-mono
**npm**: `@mariozechner/pi-coding-agent`
**Stars**: 18,200+

## Relationship to OpenClaw

OpenClaw (214K+ GitHub stars, Feb 2026) does **not** implement its own agent runtime. It builds gateway, orchestration, and multi-channel integration layers on top of Pi's `AgentSession`. OpenClaw handles WhatsApp/Telegram/Discord/Slack/Signal/iMessage routing; Pi handles the LLM reasoning and tool execution.

OpenClaw was originally "Clawdbot" (Nov 2025), renamed to "Moltbot" after Anthropic trademark complaints (Jan 2026), then "OpenClaw" three days later. Creator Peter Steinberger joined OpenAI in Feb 2026; the project moved to an independent open-source foundation.

## Architecture

```
pi-coding-agent + pi-tui        ← CLI / embedding layer
        │
  pi-agent-core                  ← agent loop, tool execution, events
        │
      pi-ai                     ← streaming, models, multi-provider LLM
```

### Supported LLM Providers

Pi's `pi-ai` layer supports: Anthropic, OpenAI, Google (Gemini), xAI, Groq, Cerebras, OpenRouter, and any OpenAI-compatible endpoint. This means you can swap models without changing agent code.

### Extension System

Extensions are TypeScript modules loaded at runtime (via `jiti`, no pre-compilation). Lifecycle hooks:
- `onSessionStart`
- `onBeforeTurn`
- `onToolCall`
- `onToolResult`

## Embedding via SDK

The core embedding primitive is `createAgentSession()`:

```typescript
import {
  AuthStorage,
  createAgentSession,
  ModelRegistry,
  SessionManager,
} from "@mariozechner/pi-coding-agent";

const authStorage = AuthStorage.create();
const { session } = await createAgentSession({
  sessionManager: SessionManager.inMemory(),
  authStorage,
  modelRegistry: new ModelRegistry(authStorage),
});

await session.prompt("What files are in the current directory?");
```

You can pass custom tools and models:

```typescript
const { session } = await createAgentSession({
  model: myModel,
  tools: [readTool, bashTool, myCustomTool],
  sessionManager: SessionManager.inMemory(),
});
```

`createAgentSession()` uses a `ResourceLoader` to supply extensions, skills, prompt templates, themes, and context files. If not provided, it uses `DefaultResourceLoader` with standard discovery.

### AgentSession Interface

Key methods:
- `session.prompt(text)` — send a prompt, get a response
- `session.steer(text)` — queue a message during streaming
- `session.followUp(text)` — interrupt with a follow-up
- Event subscriptions for tool calls, completions, errors
- Access to `sessionId`, `model`, message history

### Running Modes

Pi runs in four modes:
1. **Interactive** — CLI with TUI
2. **Print / JSON** — single-shot, structured output
3. **RPC** — for process integration
4. **SDK** — embedding in your own apps (most relevant for InstantDemo)

## Relevance to InstantDemo

Pi could serve as the agent layer for a standalone InstantDemo product:

1. **Create custom tools** for DOM extraction, script generation, TTS, and video rendering
2. **Wire to a cheap model** (Gemini Flash, DeepSeek) via Pi's multi-provider `pi-ai` layer
3. **Use `createAgentSession()`** to run the agent loop — Pi handles tool calling, retries, conversation state
4. **Swap models freely** — test cost/quality tradeoffs without rewriting orchestration

### Cost Context (March 2026 pricing)

| Model | Input / Output per 1M tokens | Notes |
|---|---|---|
| Gemini 2.5 Flash | $0.15 / $0.60 | Hybrid reasoning, flat pricing across context lengths |
| Gemini 2.0 Flash-Lite | $0.075 / $0.30 | Cheapest mainstream option |
| DeepSeek V3.2 | $0.28 / $0.42 | Cache hits at $0.028/M — great for repeated DOM patterns |
| Claude Sonnet | $3.00 / $15.00 | Higher quality but 20-40x more expensive than Flash |

For a DOM analysis + script generation task, token volume is dominated by input (the DOM). A typical page DOM might be 50-100K tokens. At Gemini Flash pricing, that's ~$0.01-0.02 per generation. DeepSeek with caching could be even cheaper for repeated analyses of the same site.

## Resources

- [Pi GitHub repo](https://github.com/badlogic/pi-mono)
- [SDK docs](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/sdk.md)
- [SDK examples](https://github.com/badlogic/pi-mono/tree/main/packages/coding-agent/examples)
- [Extensions docs](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/extensions.md)
- [How to Build a Custom Agent Framework with PI — Nader Dabit](https://nader.substack.com/p/how-to-build-a-custom-agent-framework)
- [Inside OpenClaw: How It Works — DEV Community](https://dev.to/jiade/inside-openclaw-how-the-worlds-fastest-growing-ai-agent-actually-works-under-the-hood-4p5n)
- [Pi: The Minimal Agent Within OpenClaw — Armin Ronacher](https://lucumr.pocoo.org/2026/1/31/pi/)
- [OpenClaw Wikipedia](https://en.wikipedia.org/wiki/OpenClaw)
