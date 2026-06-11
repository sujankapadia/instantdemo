import { Loader2 } from 'lucide-react'

interface RunInProgressBannerProps {
  runId: string
}

/**
 * Shown when state.json says a run is in flight (current_run_id is
 * set) but the local useRun hook isn't tracking it — typically
 * because the browser was refreshed mid-run. We can't reconnect to
 * the SSE stream and replay events (no server-side buffering yet),
 * so the best we can do is acknowledge the run and tell the user to
 * wait for it to finish before refreshing again.
 */
export function RunInProgressBanner({ runId }: RunInProgressBannerProps) {
  return (
    <div
      className="flex items-center gap-3 border-b border-border bg-secondary/40 px-4 py-2 text-foreground/90"
      data-run-id={runId}
    >
      <Loader2 className="size-4 shrink-0 animate-spin" />
      <div className="text-sm">
        The studio was still working when this page reloaded. Give it
        a minute, then refresh to see where things stand.
      </div>
    </div>
  )
}
