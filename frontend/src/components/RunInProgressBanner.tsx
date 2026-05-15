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
    <div className="flex items-center gap-3 border-b border-sky-500/30 bg-sky-500/10 px-4 py-2 text-sky-200">
      <Loader2 className="size-4 shrink-0 animate-spin" />
      <div className="text-sm">
        A run is in progress (
        <code className="font-mono text-xs">{runId.slice(0, 8)}…</code>
        ). The browser was refreshed during the run, so the live
        agent log isn't visible. Wait for the run to complete and
        refresh again to see results.
      </div>
    </div>
  )
}
