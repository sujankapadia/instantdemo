// Mirrors Pydantic models in src/instantdemo/server/routes/runs.py.
// Hand-maintained for now.

// Mirrors instantdemo.server.routes.runs.IntentBody (which mirrors
// the engine's instantdemo.intent.Intent dataclass). See issue #39.
export interface Intent {
  goal: string
  audience: string | null
  tone: string | null
  focus: string[]
  excludes: string[]
  addenda: string[]
}

export function emptyIntent(): Intent {
  return {
    goal: '',
    audience: null,
    tone: null,
    focus: [],
    excludes: [],
    addenda: [],
  }
}

export interface RunRequest {
  phases: number[]
  url: string
  describe?: string | null
  source?: string | null
  tts?: string
  pause_between_phases?: boolean
  intent?: Intent | null
  // Optional product one-pager / README excerpt (M1). Persisted to
  // product-context.md and injected into Phase 1's prompt.
  docs?: string | null
  // Scoped chapter revision (M5b): re-plan/re-record ONE chapter.
  section_scope?: string | null
  section_instruction?: string | null
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
  | {
      // M7: phases 2-4 work chapter by chapter; this drives the
      // header's "chapter 3 of 8" suffix.
      type: 'chapter_progress'
      phase: number
      current: number
      total: number
      name: string
    }
  | {
      // M8: the renderer reports each segment as it narrates (TTS)
      // and records — drives the header's "recording scene 5 of 21".
      type: 'render_progress'
      phase: number
      stage: 'narrating' | 'recording'
      current: number
      total: number
    }
  | { type: 'screenshot'; phase: number; file: string; url: string }
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
