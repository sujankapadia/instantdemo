# MCP Server Approach

Research notes on shipping InstantDemo as an MCP server for Claude Code (and other MCP-compatible agents).

## The Idea

Instead of building a standalone SaaS with its own agent and LLM costs, ship InstantDemo as an MCP server. Users bring their own agent (Claude Code, Cursor, Windsurf, etc.) — the agent handles the reasoning (DOM analysis, script writing), and our MCP server provides the specialized tools (rendering, TTS, video assembly).

**Key insight**: the expensive part (LLM reasoning over a DOM) runs on the user's subscription. The differentiated part (turning a script into a polished video) runs on our tools.

## What an MCP Server Is

MCP (Model Context Protocol) is a standard for giving AI agents access to external tools, resources, and prompts. An MCP server exposes:

- **Tools** — functions the agent can call (like API endpoints)
- **Resources** — data the agent can read (like GET endpoints)
- **Prompts** — reusable prompt templates

Claude Code, Cursor, VS Code Copilot, OpenAI's Apps SDK, and others all support MCP. One server works across all of them.

## Proposed Tools

```
instantdemo_crawl_page(url) → structured DOM / interactive element map
instantdemo_generate_script(url, description) → demo script JSON
instantdemo_render_video(script, tts_provider, output_path) → MP4 file
instantdemo_list_voices(tts_provider) → available voices
instantdemo_preview_audio(text, tts_provider, voice) → audio sample
```

The agent orchestrates these however it wants. A typical flow:

1. User: "Make a demo video of my app at localhost:3000 showing the signup flow"
2. Agent calls `instantdemo_crawl_page("http://localhost:3000")`
3. Agent reasons about the DOM, calls `instantdemo_generate_script(...)` or writes the script JSON itself
4. Agent calls `instantdemo_render_video(script, "google", "demo.mp4")`
5. User gets a video

Alternatively, `instantdemo_generate_script` could be a pure tool that does the DOM crawl + LLM script generation internally (using a cheap model like Gemini Flash), keeping the agent's context window clean.

## Implementation

### Python (matches existing codebase)

The existing `run_demo.py` is already Python. Use the official Python MCP SDK (`mcp`):

```python
from mcp.server import Server
from mcp.server.stdio import stdio_server

server = Server("instantdemo")

@server.tool()
async def render_video(script: dict, tts_provider: str = "google", output: str = "demo.mp4") -> str:
    """Render a demo video from a script definition."""
    # ... existing pipeline logic from run_demo.py ...
    return f"Video rendered to {output}"

@server.tool()
async def crawl_page(url: str) -> dict:
    """Extract interactive elements and page structure from a URL."""
    # Playwright headless crawl, return structured DOM
    ...

async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write)
```

### TypeScript alternative

If we want to align with the broader MCP ecosystem (most servers are TypeScript):

```typescript
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const server = new McpServer({ name: "instantdemo", version: "0.1.0" });

server.tool("render_video",
  { script: z.object({...}), tts_provider: z.string(), output: z.string() },
  async ({ script, tts_provider, output }) => {
    // shell out to run_demo.py or reimplement in TS
    return { content: [{ type: "text", text: `Video rendered to ${output}` }] };
  }
);

const transport = new StdioServerTransport();
await server.connect(transport);
```

### Recommendation: Python

Stay in Python. The pipeline already works, Playwright's Python API is what we use, and the Python MCP SDK is mature. No reason to rewrite in TypeScript.

## Installation & Distribution

### Local (development)

```bash
# User adds the server to Claude Code
claude mcp add instantdemo -- python /path/to/instantdemo/server.py

# Or with uvx (no clone needed, if published to PyPI)
claude mcp add instantdemo -- uvx instantdemo
```

### PyPI package

Publish as `instantdemo` on PyPI. Users install with:

```bash
claude mcp add instantdemo -- uvx instantdemo
```

This is the standard distribution path for Python MCP servers. No manual config files needed.

### Docker (for users who don't want Python deps)

```bash
claude mcp add instantdemo -- docker run -i --rm instantdemo/server
```

Bundles Python, Playwright, Chromium, ffmpeg — heavier but zero-dependency for the user.

## Monetization

The MCP ecosystem is developing monetization infrastructure:

| Platform | Model | Revenue share |
|---|---|---|
| **MCPize** | Hosting + payments + distribution | 85% to developer |
| **Apify** | Pay-per-event, auto-distribution to Make/n8n/Zapier | Revenue per charge function call |
| **MCP Hive** | Pay-per-request marketplace (launching May 2026) | Per-response earnings |
| **MCP Market** | Discovery marketplace | Listing + traffic |

Current state: 11,000+ MCP servers exist, <5% are monetized. Top creators earn $3-10K/month. The monetization layer is nascent but growing fast (8M protocol downloads, 85% MoM growth).

### Monetization options for InstantDemo

1. **Free MCP server, paid rendering API** — the server is open source, but `render_video` calls a hosted API that meters usage. Charge per render ($0.10-0.50 per video depending on length/quality).
2. **MCPize / MCP Hive listing** — let the platform handle billing. Lower friction, but platform takes a cut.
3. **Freemium** — free local rendering (user provides their own ffmpeg/Playwright), paid cloud rendering (we host the browser + TTS).
4. **Open source everything** — build reputation, monetize via consulting or a hosted product later.

Option 1 (free server, paid render API) seems like the best balance: open source for adoption, revenue from the compute-intensive step.

## Advantages

- **Zero LLM cost to us** — the user's agent (Claude Code subscription, etc.) handles all reasoning
- **Ship fast** — the rendering pipeline already works, just needs an MCP wrapper
- **Multi-agent reach** — works with Claude Code, Cursor, VS Code Copilot, any MCP client
- **Growing distribution** — MCP marketplaces and Anthropic's ecosystem are expanding rapidly
- **Natural upgrade path** — start as MCP server, add a web UI / standalone product later if demand validates

## Risks

- **Market size** — limited to MCP-compatible agent users (growing but still early)
- **Quality control** — the agent writes the script, so video quality depends on the agent's reasoning. We can mitigate with good prompt templates and a `validate_script` tool.
- **Competition** — Playwright already has an MCP server for browser automation. Our value-add is the full pipeline (crawl → script → TTS → render → video), not just browser control.
- **Dependency on MCP adoption** — if a different protocol wins, we'd need to adapt. Mitigation: the core pipeline is protocol-agnostic, the MCP layer is thin.

## Next Steps

1. Create `server.py` wrapping existing `run_demo.py` functions as MCP tools
2. Test with `claude mcp add` locally
3. Add a `crawl_page` tool using Playwright to extract interactive elements
4. Add prompt templates for common demo generation patterns
5. Publish to PyPI as `instantdemo`
6. List on MCP Market / MCPize for discovery

## Resources

- [MCP specification](https://modelcontextprotocol.io)
- [Python MCP SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Claude Code MCP docs](https://code.claude.com/docs/en/mcp)
- [Build an MCP server](https://modelcontextprotocol.io/docs/develop/build-server)
- [Playwright MCP server](https://github.com/modelcontextprotocol/servers) (reference for browser automation patterns)
- [MCPize — monetization platform](https://mcpize.com)
- [MCP Hive — marketplace](https://mcp-hive.com)
- [Distributing MCP servers — Speakeasy](https://www.speakeasy.com/mcp/distributing-mcp-servers)
- [Building the MCP Economy — Cline blog](https://cline.bot/blog/building-the-mcp-economy-lessons-from-21st-dev-and-the-future-of-plugin-monetization)
