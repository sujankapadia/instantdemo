# OpenCode Approach

Research notes on using OpenCode as the agent runtime for InstantDemo.

## What OpenCode Is

OpenCode is an open-source (MIT license) AI coding agent built in Go. It's similar to Claude Code but model-agnostic and free — users bring their own API keys (BYOK) for whatever provider they want. Available as a CLI, desktop app, and IDE extension (VS Code, Cursor, JetBrains, Zed, Neovim, Emacs).

**GitHub**: https://github.com/sst/opencode (by SST / Anomaly)
**Site**: https://opencode.ai
**Models**: 75+ supported — Claude, OpenAI, Gemini, DeepSeek, xAI, local models, any OpenAI-compatible endpoint

### Pricing

- **OpenCode itself**: Free and open source (MIT)
- **BYOK**: Users connect their own API keys (Anthropic, OpenAI, Google, etc.) and pay the provider directly
- **OpenCode Go**: Optional pay-as-you-go credits for bundled model access (cheap models like GLM-5, Kimi K2.5, MiniMax)
- **OpenCode Zen**: $10/month subscription with generous rate limits on bundled models

## Why This Is Interesting for InstantDemo

OpenCode gives us a **free, open-source agent runtime with a programmatic SDK**. Unlike Claude Code (subscription, closed source) or Pi (TypeScript-only), OpenCode lets us:

1. Ship a pre-configured agent that users run for free
2. Point it at the cheapest model that works (Gemini Flash, DeepSeek)
3. Control the full experience — system prompt, tools, permissions
4. Embed it programmatically in a server or automation pipeline

The user's only cost is model API fees, which could be as low as $0.01-0.02 per demo generation with Gemini Flash.

## Programmatic SDK

OpenCode has a JS/TS SDK (`@opencode-ai/sdk`) auto-generated from an OpenAPI spec:

```typescript
import { createOpencode, createOpencodeClient } from "@opencode-ai/sdk";

// Option 1: Spin up server + client together
const { client, server } = await createOpencode({
  hostname: "127.0.0.1",
  port: 4096,
  timeout: 5000,
});

// Option 2: Connect to an already-running instance
const client = createOpencodeClient({
  baseUrl: "http://127.0.0.1:4096",
});

// Create a session and send a prompt
const { data: session } = await client.session.create();
await client.session.prompt({
  path: { id: session.id },
  body: {
    parts: [{ type: "text", text: "Generate a demo video script for localhost:3000" }],
  },
});
```

Types are importable: `import type { Session, Message, Part } from "@opencode-ai/sdk"`

### Other Programmatic Modes

| Mode | How | Use case |
|---|---|---|
| **Non-interactive CLI** | `opencode "prompt here" --json` | Scripting, one-shot generation |
| **HTTP server** | `opencode serve` | Remote access, web integration |
| **ACP server** | `opencode acp` (stdin/stdout nd-JSON) | IDE integration |
| **SDK** | `createOpencode()` | Full programmatic control |

## Custom Agents

Agents are defined as markdown files in `~/.config/opencode/agents/` or `.opencode/agents/`. You can also create them with `opencode agent create`.

Example agent config for InstantDemo:

```yaml
# .opencode/agents/instantdemo.yaml (conceptual — actual format is markdown)
name: instantdemo
model: gemini-2.5-flash
color: '#00d4aa'
tools:
  read: true
  bash: true
  write: true
  grep: true
  # custom MCP tools also available
permissions:
  edit: allow
  external_directory: deny
```

The agent gets a custom system prompt (in a separate markdown file) with instructions specific to demo generation — how to analyze a page, what makes a good demo script, the JSON schema to produce, etc.

## Custom Tools

Custom tools are defined with `Tool.define()` in TypeScript/JavaScript:

```typescript
Tool.define({
  name: "render_video",
  description: "Render a demo video from a script definition",
  parameters: {
    script: { type: "object", description: "Demo script JSON" },
    tts_provider: { type: "string", enum: ["google", "piper", "elevenlabs"] },
    output: { type: "string", description: "Output file path" },
  },
  async execute({ script, tts_provider, output }) {
    // Call into the Python rendering pipeline
    // ...
    return { text: `Video rendered to ${output}` };
  },
});
```

Custom tools integrate with OpenCode's permission, validation, and truncation systems automatically.

## MCP Integration

OpenCode is also an MCP client. Configure MCP servers in `opencode.json`:

```json
{
  "mcp": {
    "instantdemo": {
      "command": "uvx",
      "args": ["instantdemo"],
      "permission": "allow"
    }
  }
}
```

This means our MCP server approach (see `docs/mcp-server-approach.md`) works with OpenCode too — not just Claude Code. Users could choose either agent.

## How It Would Work End-to-End

1. User installs OpenCode (free) and sets up a Gemini Flash API key
2. User clones or installs our InstantDemo agent config + custom tools (or adds our MCP server)
3. User runs: `opencode -a instantdemo "Make a demo video of my app at localhost:3000 showing the signup flow"`
4. OpenCode (with Gemini Flash) crawls the page, reasons about the DOM, generates a script, calls our render tool
5. User gets an MP4

**Total cost to user**: ~$0.01-0.02 per generation (Gemini Flash API fees). No subscription, no platform fee.

## Comparison with Other Approaches

| | MCP Server | Pi Agent SDK | OpenCode |
|---|---|---|---|
| **Agent runtime** | User's existing agent (Claude Code, Cursor, etc.) | Pi's AgentSession | OpenCode |
| **Cost to user** | Their existing subscription | Model API fees | Model API fees |
| **Cost to us** | Zero (or per-render if hosted) | Zero | Zero |
| **Model flexibility** | Limited by host agent | Any via pi-ai | Any (75+ models) |
| **Programmatic embedding** | N/A (tool only) | `createAgentSession()` | `createOpencode()` SDK |
| **Distribution** | PyPI / npm / MCP marketplace | npm package | Agent config + tools |
| **User setup** | One command (`claude mcp add`) | Code integration | Install OpenCode + config |
| **Open source** | Our server is, host agent may not be | Yes (MIT) | Yes (MIT) |

### OpenCode vs Pi for a standalone product

- **OpenCode** gives you the full CLI/TUI out of the box — users get an interactive experience without us building UI. But we're coupling to OpenCode's agent loop and update cycle.
- **Pi** gives lower-level embedding — better for building our own product experience (web app, API server), but we'd need to build the user-facing layer ourselves.

OpenCode is the better choice if we want to **ship fast with zero UI work**. Pi is the better choice if we want to **build a standalone product with full control**.

## Risks

- **Go + TypeScript mismatch** — OpenCode is Go, our pipeline is Python. Custom tools are JS/TS, so the render step would need to shell out to Python or rewrite in TS. MCP server approach avoids this (Python server, OpenCode just calls it).
- **Dependency on OpenCode project** — it's open source and MIT, but still a young project. If development stalls or direction changes, we're exposed.
- **User setup friction** — more steps than a pure MCP server (install OpenCode, configure API key, add agent config). Could be mitigated with a setup script.

## Next Steps

1. **Fastest path**: Build the MCP server (Python, matches existing code), test it works with both Claude Code and OpenCode
2. **Then**: Create an OpenCode agent config (system prompt + tool permissions) that's optimized for demo generation with Gemini Flash
3. **Package both**: users choose their preferred agent, our MCP server works with either

## Resources

- [OpenCode docs](https://opencode.ai/docs/)
- [OpenCode SDK](https://opencode.ai/docs/sdk/)
- [OpenCode Agents](https://opencode.ai/docs/agents/)
- [OpenCode Custom Tools](https://opencode.ai/docs/custom-tools/)
- [OpenCode MCP Servers](https://opencode.ai/docs/mcp-servers/)
- [OpenCode CLI](https://opencode.ai/docs/cli/)
- [OpenCode Config](https://opencode.ai/docs/config/)
- [OpenCode Providers](https://opencode.ai/docs/providers/)
- [How Coding Agents Actually Work: Inside OpenCode — Moncef Abboud](https://cefboud.com/posts/coding-agents-internals-opencode-deepdive/)
- [OpenCode vs Claude Code — OpenAIToolsHub](https://www.openaitoolshub.org/en/blog/opencode-vs-claude-code)
