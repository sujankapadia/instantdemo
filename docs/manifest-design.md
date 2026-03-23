# Design: Demo Manifest for URL-Based Video Generation

## Problem

The current skill works well because Claude Code has full source code access — it reads routes, components, and docs to produce accurate demo scripts on the first try. But the original product vision is to generate demo videos from just a URL, without source code access.

A blind URL crawl gets you interactive elements (buttons, links, inputs) but misses:
- **Product knowledge** — what the app does, who it's for, what to emphasize
- **UI map** — all routes/pages, their purpose, how they connect
- **Auth** — how to log in, dev/demo credentials
- **Data state** — how to get the app into a demo-ready state (seed data, fixtures)
- **Navigation structure** — which links are nav links vs. in-page actions, SPA vs. full reload

Without this context, the agent guesses what to demo, picks wrong selectors, misses pages behind auth, and takes multiple iterations to produce a usable script.

## Solution: The Demo Manifest

A structured YAML file (`instantdemo.yaml`) that captures the context a crawl would miss. The developer creates it once (or generates it with a companion tool), and the rendering utility consumes it without needing source code access.

### Manifest schema

```yaml
# instantdemo.yaml

product:
  name: "Acme Dashboard"
  description: "Real-time analytics for e-commerce stores"
  audience: "Store owners and marketing teams"
  value_prop: "See revenue, orders, and traffic in one place — updated in real time"

app:
  url: "http://localhost:3000"
  framework: "react"           # react | nextjs | vue | svelte | angular | other
  spa: true                    # if true, use nav links instead of goto for page transitions

auth:
  login_url: "/login"
  credentials:
    email: "demo@example.com"
    password: "demo123"
  selectors:
    email: "input[name='email']"
    password: "input[name='password']"
    submit: "button[type='submit']"

pages:
  - path: "/"
    name: "Dashboard"
    description: "Overview with revenue, orders, and traffic charts. Data loads from API on mount."
    nav_selector: "a[href='/']"
    wait_for: "[data-testid='dashboard-loaded']"
    notes: "Has SSE connection for real-time updates — don't use networkidle"

  - path: "/orders"
    name: "Orders"
    description: "List of recent orders with status filters. Virtualized list, scrollable."
    nav_selector: "a[href='/orders']"
    wait_for: "[data-testid='orders-table']"

  - path: "/orders/:id"
    name: "Order Detail"
    description: "Single order with line items, shipping status, and customer info."
    nav_selector: null          # reached by clicking a row in /orders
    wait_for: "[data-testid='order-detail']"

  - path: "/analytics"
    name: "Analytics"
    description: "Traffic sources, conversion funnels, and cohort analysis charts."
    nav_selector: "a[href='/analytics']"
    wait_for: ".chart-container canvas"

data_setup:
  command: "npm run seed"
  description: "Seeds the database with 30 days of sample orders and traffic data"
  verify: "curl -s http://localhost:3000/api/health | jq .seeded"

narration:
  tone: "casual"               # casual | formal | technical
  audience: "non-technical"    # technical | non-technical
  terminology:
    - "We call the main page the Dashboard, not the Home page"
    - "Orders are called 'transactions' in the codebase but 'orders' in the UI"

demo_suggestions:
  - name: "Product overview"
    description: "Quick tour: dashboard metrics → order list → order detail → analytics"
    pages: ["/", "/orders", "/orders/:id", "/analytics"]
    duration: "45s"

  - name: "Order management"
    description: "Filter orders by status, click into a detail, see shipping timeline"
    pages: ["/orders", "/orders/:id"]
    duration: "30s"

  - name: "Analytics deep dive"
    description: "Show traffic sources chart, hover for details, switch to funnel view"
    pages: ["/analytics"]
    duration: "30s"
```

### What each section provides

| Section | What the crawl would miss | What the manifest provides |
|---|---|---|
| `product` | What the app does and why it matters | Name, description, audience, value prop — the "story" behind the demo |
| `app` | Whether it's an SPA, what framework | Framework hint, SPA flag (use nav links vs. goto) |
| `auth` | How to get past the login page | Credentials, login URL, form selectors |
| `pages` | Route names, purpose, relationships | Every page with a human description, nav selector, wait condition |
| `data_setup` | Whether the app has data loaded | Seed command, verification check |
| `narration` | What tone and terminology to use | Style preferences, product-specific language |
| `demo_suggestions` | What's worth demoing | Pre-planned flows with page sequences and target duration |

## Companion Utility: `instantdemo init`

A CLI tool that generates the manifest from source code. The developer runs it once in their project:

```bash
instantdemo init
```

The tool:

1. **Reads routes** — detects the framework (React Router, Next.js pages/, SvelteKit routes/, Vue Router) and extracts all route paths
2. **Reads page components** — for each route, reads the top-level component to extract:
   - A description (from comments, component name, or LLM summary)
   - `data-testid` attributes or other stable selectors
   - Wait conditions (loading states, data dependencies)
3. **Reads layout/nav** — finds the nav component to extract `nav_selector` for each route
4. **Reads README/docs** — extracts product name, description, audience
5. **Finds seed scripts** — looks for `seed.py`, `fixtures.json`, `prisma/seed.ts`, `docker-compose` with DB init
6. **Finds auth config** — looks for `.env.example`, auth middleware, login components
7. **Suggests demo flows** — based on route structure and page descriptions

Output: `instantdemo.yaml` in the project root, pre-filled with everything it found. The developer reviews, corrects selectors, adds credentials, tweaks descriptions. This takes a few minutes — it's a one-time setup.

### How `init` could work across environments

| Environment | How init works |
|---|---|
| Developer's local machine (with source) | Reads source code directly — best results |
| Claude Code session | The skill already does this in Phases 1-3 — `init` would be a non-interactive version that outputs a manifest instead of a script |
| CI/CD pipeline | Reads source code from the repo at build time |
| No source access | Falls back to crawling the running app + prompting the user for product context |

## Rendering Utility: `instantdemo render`

Consumes the manifest to generate a demo video without source code:

```bash
instantdemo render --manifest instantdemo.yaml --flow "Product overview" --tts google -o demo.mp4
```

Steps:

1. Read the manifest
2. Run `data_setup.command` if needed, verify with `data_setup.verify`
3. Log in using `auth` credentials and selectors
4. Select the requested flow from `demo_suggestions`
5. Generate a demo script JSON from the flow's page sequence + page descriptions + product context
   - This is the LLM step — uses the manifest context to write narration and choose actions
   - Can use a cheap model (Gemini Flash, DeepSeek) since the manifest provides most of the context
6. Validate the script (check selectors exist, pages load)
7. Render the video using the existing pipeline (TTS → Playwright → ffmpeg)

### LLM usage in the render step

The manifest reduces LLM work dramatically. Instead of "analyze this DOM and figure out what to demo," the prompt becomes:

> Given this product description, these pages with their descriptions and selectors, and this flow specification, write narration for each segment and choose the right actions.

This is a structured generation task — low token count, high quality, works well with cheap models. The manifest is the context the LLM needs, not the DOM.

## The two-tool split

| Tool | Input | Output | Needs source code? | Needs LLM? |
|---|---|---|---|---|
| `instantdemo init` | Source code (routes, components, docs) | `instantdemo.yaml` | Yes | Optional (for descriptions) |
| `instantdemo render` | `instantdemo.yaml` + running app | MP4 video | No | Yes (for narration) |

The manifest is the bridge between source-aware generation and URL-based rendering.

## Distribution and workflow

### For developers (current audience)

```bash
# One-time setup
instantdemo init              # generates instantdemo.yaml
# Review and edit the manifest

# Per video
instantdemo render --flow "Product overview" --tts google
```

### For CI/CD (automated demo updates)

```yaml
# .github/workflows/demo.yml
- run: instantdemo render --manifest instantdemo.yaml --flow "Product overview" --tts google -o demo.mp4
- uses: actions/upload-artifact@v4
  with:
    name: demo-video
    path: demo.mp4
```

Push a UI change → demo video updates automatically.

### For non-developers (future product)

A web UI where users:
1. Upload or link their `instantdemo.yaml` (or fill out a form that generates one)
2. Select a flow
3. Choose a voice
4. Click render
5. Download the MP4

The manifest format is the product API — simple enough for non-developers to edit, structured enough for machines to consume.

## Manifest as a well-known location

For hosted apps, the manifest could live at a well-known URL:

```
https://app.example.com/.well-known/instantdemo.json
```

This enables a one-command experience:

```bash
instantdemo render --url https://app.example.com --flow "Product overview"
```

The tool fetches the manifest from the well-known URL, then proceeds with rendering. No manifest file needed locally.

## Relationship to the current skill

The current Claude Code skill is `init` + `render` combined — it reads source code (init) and produces a script (render) in one interactive session. The manifest approach separates these concerns:

- The skill becomes the best way to **create** the manifest (source-code-aware, interactive, high quality)
- The CLI becomes the best way to **consume** the manifest (automated, repeatable, no source needed)

They're complementary, not competing.

## Open questions

- **Manifest versioning** — how to handle schema changes as the format evolves?
- **Page parameters** — dynamic routes (`/orders/:id`) need example data. Should the manifest include sample IDs?
- **Multi-environment** — staging vs. production URLs. Support for environment overrides?
- **Internationalization** — narration language, page content language. Separate manifests per locale?
- **Manifest validation** — a `instantdemo validate` command to check the manifest against a running app?
