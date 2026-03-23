# Monetization Ideas

The core pipeline (TTS + Playwright + ffmpeg) is commodity — easy to replicate, all open source components. These ideas focus on where value could exist beyond the pipeline itself.

## 1. Hosted Rendering

The user doesn't install anything. They provide a manifest (or a URL with a well-known endpoint), pick a voice and flow, and get an MP4 back.

**What you're selling**: convenience and compute. No Playwright install, no Chromium binary, no ffmpeg, no TTS API keys to manage. Upload → render → download.

**How it works**:
- Web UI or API endpoint
- User uploads `instantdemo.yaml` or points to `https://app.example.com/.well-known/instantdemo.json`
- Selects a flow from `demo_suggestions`, picks a TTS voice
- Server runs the rendering pipeline, returns an MP4
- Charge per render ($0.25-1.00 depending on length/voice quality)

**Costs**: TTS API fees (~$0.01-0.05 per render for Google WaveNet), server compute for headless Chromium + ffmpeg (~$0.01-0.05 per render on a beefy VM). Margins are thin but real at volume.

**Who wants this**: developers who want a quick demo video without setting up a local pipeline, CI/CD pipelines that auto-generate videos on deploy, non-technical team members who can't run CLI tools.

**The iteration problem**: demo videos typically take 3-5 attempts to get right — tweaking narration, adjusting selectors, reordering segments. If every attempt is a full render, the user is paying for failed attempts or you're eating the compute cost. The current CLI skill solves this by separating script generation (cheap, iterative, local) from rendering (expensive, one-shot). A hosted service needs a different approach:

- **Preview mode** — render a low-quality fast preview (lower resolution, skip TTS or use a cheap local TTS, faster encoding). The user checks timing and flow without paying for a full render. Only the final "publish" render uses full quality TTS and high-res encoding. Previews are free or very cheap.

- **Script editor with visual context** — a web UI showing the script alongside screenshots of what each segment looks like (captured via Playwright, not a live interactive browser). The user edits narration text, reorders segments, and adjusts pacing — with visual confirmation that each segment shows the right page state. Selectors come from the manifest or `init`, not from the user clicking through a live preview (if you're clicking through the app to pick elements, you might as well just record with Loom). Only render the actual video when the script is finalized. Moderate development cost for a good user experience.

- **Charge per published video, not per render** — unlimited draft renders, pay only when you export the final MP4. Aligns incentives: the user iterates freely, you only charge for the output they're happy with. The downside is that draft renders still cost server-side compute (Playwright instances, TTS calls), so you need to cap draft renders or use cheaper resources for them.

The third option is probably the most honest pricing model, possibly combined with preview mode for draft renders to keep costs down.

## 2. Voice Quality / Custom Voices

Free tier uses Piper (robotic, local) or Google WaveNet (decent, free tier). Paid tier unlocks premium voices.

**What you're selling**: the voice is personal and not replicable. A founder's cloned voice narrating their product demo is compelling in a way that a generic TTS voice isn't.

**Tiers**:
- **Free**: Piper (local, robotic) or Google WaveNet (natural, limited)
- **Pro**: ElevenLabs voices (near-human quality, large voice library)
- **Custom**: voice cloning — the user records 30 seconds of speech, gets a cloned voice for all their demos. Their voice, their brand.

**How it works**:
- Integration with ElevenLabs voice cloning API or similar
- User records a voice sample via the web UI
- Cloned voice is stored and reusable across all future renders
- Could also offer "brand voice packs" — professional voice actors with specific tones (authoritative, friendly, technical)

**Who wants this**: founders who appear in their own content, companies with brand voice guidelines, developer advocates who want consistency across videos.

## 3. Manifest as a Platform

The interesting asset isn't the pipeline — it's the manifest format. If `instantdemo.yaml` becomes how apps describe themselves for demo generation, services can be built on top of it.

**What you're selling**: the ecosystem around the manifest, not the rendering.

**Possibilities**:
- **Demo template marketplace** — browse and install pre-built demo flows for common app patterns (SaaS dashboard, e-commerce storefront, developer tool CLI). Developers fork a template and customize for their app.
- **Demo analytics** — which flows get rendered most, where viewers drop off (if videos are hosted), which narration styles perform best. Data-driven demo optimization.
- **A/B testing** — render two versions of a demo with different narration or flow order, test which converts better on a landing page.
- **Community manifests** — open source projects publish their `instantdemo.yaml` so anyone can generate a demo video. The manifest becomes part of the project's documentation.

**Who wants this**: SaaS companies optimizing their demo-to-signup funnel, open source maintainers who want contributor-friendly demo generation.

**Reality check**: this only works with significant adoption of the manifest format. Chicken-and-egg problem — need users to attract templates, need templates to attract users.

## 4. Enterprise Features

The pipeline becomes a feature in a larger platform for teams that produce demos at scale.

**What you're selling**: workflow, consistency, and collaboration — not just rendering.

**Features**:
- **Brand kits** — logo overlays, intro/outro sequences, consistent color scheme, approved fonts. Every video looks like it came from the same company.
- **Team accounts** — shared manifests, shared voice settings, shared brand kit. New team member generates a demo that looks identical to everyone else's.
- **Approval workflows** — script review before rendering. Marketing approves narration, engineering approves selectors. Nobody renders a video with wrong terminology.
- **Auto-publish integrations** — render completes → auto-upload to docs site, Notion, Confluence, YouTube, S3. No manual download/upload step.
- **Version history** — every rendered video is tracked with its script, manifest version, and TTS settings. Roll back to a previous version, diff two scripts.
- **Scheduled re-renders** — nightly or weekly re-render of all demos against staging. If a selector breaks or a page changes, flag it before the video goes stale.
- **Embeddable player** — hosted video player with analytics (views, watch time, drop-off points). Paste an embed code into your docs or landing page.

**Who wants this**: companies with 5+ product demos (each feature, each persona, each language), developer relations teams producing weekly content, enterprise sales teams generating per-prospect demos.

**Reality check**: this is a real SaaS product, not a CLI tool. Significant investment to build and maintain. But it's where recurring revenue lives.

## The Reputation Play

Even without monetizing any of the above, demonstrating them builds credibility:

- **"I built a hosted rendering API"** → shows full-stack product thinking (infra, billing, UX)
- **"I integrated voice cloning"** → shows API integration and creative product sense
- **"I designed a manifest standard"** → shows systems thinking and developer experience chops
- **"I built team workflows with approval chains"** → shows enterprise product experience

Each of these is a portfolio piece and a conversation starter, whether or not it generates revenue. The consulting leads come from demonstrating the ability to go from idea to working product.
