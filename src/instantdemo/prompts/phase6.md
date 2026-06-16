Drift check the demo script against the live app, then signal whether
to render.

By this point Phase 4 (Explore) has already verified every selector
against the live app. Your job is only to confirm nothing has drifted
between Explore and now — the app could have restarted, data could
have been wiped, the user could have edited the script after Explore
ran. You are NOT re-probing every selector.

You have `Read` access to the demo script and `Bash` for `curl`
and a small Playwright smoke check.

### Checks

1. **App reachability**. `curl` the first segment's `goto` URL and
   any other distinct `goto` URLs in the script. 200/300 = fine.
   4xx/5xx or connection refused = the app isn't running.

2. **First-action smoke**. Write a small Playwright probe that
   loads the first `goto` URL and confirms the *first segment after
   goto* that requires a selector resolves via `wait_for_selector`
   (10s timeout). If the very first interactive step in the flow
   doesn't resolve, the renderer is guaranteed to abort, so we
   block here.

   Don't probe every segment. That's Explore's job and was already
   done; doing it again wastes tokens. The smoke check exists to
   catch the "Explore passed, now the app is in a different state"
   case.

### Output

Report your verdict as a single object with two fields:

- `directive`: exactly `RENDER_OK` or `RENDER_BLOCKED`
- `reason`: a one-sentence cause — required when `RENDER_BLOCKED`,
  may be empty for `RENDER_OK`

As fenced JSON:

```json
{"directive": "RENDER_OK", "reason": ""}
```

**Strict policy: any selector failure observed during this drift
check is RENDER_BLOCKED.** There is no "non-critical" loophole.
If the smoke selector resolves and the URLs are reachable, emit
`RENDER_OK`. Anything else is `RENDER_BLOCKED`. Validation already
happened upstream — by the time we're here, the bar is "is the app
still in the state Explore observed?"

Do not run the renderer yourself. The runner handles that after
reading your directive.
