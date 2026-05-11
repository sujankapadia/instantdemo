// Mirrors Pydantic models in src/instantdemo/server/routes/runs.py.
// Hand-maintained for now.

export interface RunRequest {
  phases: number[]
  url: string
  describe?: string | null
  source?: string | null
  tts?: string
  pause_between_phases?: boolean
}

export interface RunInfo {
  run_id: string
  phases: number[]
  started_at: string
}

export type RunEvent =
  | { type: 'phase_started'; phase: number; phase_name: string; ts: string }
  | { type: 'text_chunk'; session_id: string; text: string }
  | { type: 'tool_use'; session_id: string; tool: string; tool_input: unknown }
  | {
      type: 'phase_complete'
      phase: number
      phase_name: string
      cost_usd: number
      duration_ms: number | null
      num_turns: number | null
    }
  | { type: 'phase_error'; phase: number; error: string }
  | { type: 'paused'; completed_phase: number; next_phase: number }
  | { type: 'resumed'; next_phase: number }
  | { type: 'run_complete'; total_cost_usd: number }
  | { type: 'run_canceled' }
  | { type: 'run_error'; error: string }

export async function continueRun(runId: string): Promise<void> {
  const res = await fetch(`/api/runs/${runId}/continue`, { method: 'POST' })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
}

export async function startRun(req: RunRequest): Promise<RunInfo> {
  const res = await fetch('/api/runs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    let msg = `HTTP ${res.status}`
    try {
      const body = (await res.json()) as { detail?: string }
      if (body.detail) msg = body.detail
    } catch {
      // body wasn't JSON; fall through with HTTP code
    }
    throw new Error(msg)
  }
  return (await res.json()) as RunInfo
}

export async function cancelRun(runId: string): Promise<void> {
  const res = await fetch(`/api/runs/${runId}/cancel`, { method: 'POST' })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
}

export interface StreamSubscription {
  close: () => void
}

export function subscribeToRunStream(
  runId: string,
  onEvent: (event: RunEvent) => void,
  onError?: (err: unknown) => void,
): StreamSubscription {
  const eventSource = new EventSource(`/api/runs/${runId}/stream`)

  const messageHandler = (msg: MessageEvent<string>) => {
    try {
      const event = JSON.parse(msg.data) as RunEvent
      onEvent(event)
    } catch (err) {
      if (onError) onError(err)
    }
  }
  eventSource.addEventListener('message', messageHandler)

  // sse-starlette emits `event: heartbeat` every ~15s. We don't act on
  // them but consuming the listener prevents EventSource from logging
  // an unhandled event.
  eventSource.addEventListener('heartbeat', () => {})

  eventSource.addEventListener('error', (err) => {
    if (onError) onError(err)
    // EventSource auto-reconnects on transient errors. We rely on the
    // run_complete / run_canceled / run_error events to close the
    // stream from the consumer side via close().
  })

  return {
    close: () => {
      eventSource.removeEventListener('message', messageHandler)
      eventSource.close()
    },
  }
}
