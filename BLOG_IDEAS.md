# Blog post ideas — Claude Agent SDK patterns

## Multi-phase workflows on a single Claude Agent SDK client

A genuinely interesting pattern that's non-obvious from the docs.
Most SDK examples are single-shot (`query()` once per script
run), so devs intuitively reach for "one client per phase" when
they need phased work. Three things combine into something that
doesn't show up in the docs:

1. **One long-lived `ClaudeSDKClient`** instead of spinning up
   a new subprocess per phase. Cheaper (no per-phase auth
   handshake / process startup), simpler lifecycle.

2. **`session_id` per phase for clean conversation boundaries**
   — `client.query(prompt, session_id="phase2")` keeps each
   phase's message history isolated even though it's the same
   client process. The SDK supports this but the docs treat
   session_id as more of an implementation detail.

3. **`PreToolUse` hook + a phase dispatcher for per-phase tool
   allowlists** — and crucially, the discovery that
   `can_use_tool` doesn't fire under `bypassPermissions`. The
   dispatcher class with a mutable `current_phase` attribute
   that the orchestrator sets before each query is the
   workaround. That single discovery is probably worth its own
   paragraph because it's a footgun other SDK users will hit.

### Suggested framing

A "multi-phase workflows on one SDK client" pattern, not a
product post. Can be shown with a generic 5-phase pipeline (or
even just 2 phases) without revealing what InstantDemo does.
Code samples for the dispatcher class and the hook registration
are concrete enough to be useful; a sequence diagram (1 query →
1 client → session_id routing → PreToolUse hook → tool
allow/deny) would land the mental model in seconds.

### Audience / tone / length

- **Audience**: developers building with the Claude Agent SDK
- **Tone**: technical, focused on the pattern not the product
- **Length**: probably 1500-2500 words
- **Code**: dispatcher class + hook registration is enough
- **Diagram**: optional but high-leverage

### Working title options

- "Running multi-phase workflows on a single Claude Agent SDK client"
- "Per-phase tool allowlists with one Claude SDK client"
- "Session IDs and PreToolUse hooks: phased workflows without the process churn"

---

## Follow-up post ideas

Don't try to cram all of these into the first post. Save for
later posts so each lands a focused mental model.

### Streaming tokens from the SDK to a UI

- `include_partial_messages=True` and consuming `StreamEvent`
  with `content_block_delta` events
- Pumping the deltas through an SSE endpoint to a React frontend
- Fallback to `AssistantMessage` `TextBlock` for cases where no
  deltas fired (billing errors etc.)

### Detecting billing / auth errors from the SDK

- `AssistantMessage.error` carries errors that *aren't*
  `ResultMessage.is_error`
- The "credit balance is too low" failure mode arrives as a
  text message, not an exception
- Recommended detection logic

### Cancellation semantics

- Distinguishing `asyncio.CancelledError` from genuine failures
- Why "user clicked Cancel" shouldn't show up as a phase error
- The wrapping pattern: catch `CancelledError` separately,
  set status="canceled" before falling through to a generic
  error handler

### Hook ordering / order-of-events gotchas

- The hook fires before the tool actually executes — agent's
  `tool_use_id` is available for stitching with results
- Hook return value: allow / deny / modify input
- Why some events arrive out of order under
  `include_partial_messages`
