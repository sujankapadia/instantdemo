import { useCallback, useEffect, useRef, useState } from 'react'
import {
  cancelRun,
  continueRun,
  startRun,
  subscribeToRunStream,
  type RunEvent,
  type RunRequest,
  type StreamSubscription,
} from '@/api/runs'

export type RunStatus =
  | 'idle'
  | 'starting'
  | 'running'
  | 'paused'
  | 'complete'
  | 'canceled'
  | 'error'

export interface PhaseUpdate {
  status: 'running' | 'complete' | 'error'
  cost_usd?: number
  duration_ms?: number | null
  num_turns?: number | null
  error?: string
}

type LogEntryInput =
  | { kind: 'phase_started'; phase: number; phase_name: string; ts: string }
  | { kind: 'text'; phase: number | null; text: string }
  | {
      kind: 'tool_use'
      phase: number | null
      tool: string
      /** First relevant argument (file path, Bash command, search
       *  pattern, URL) for display alongside the tool name. */
      arg: string | null
    }
  | {
      kind: 'phase_complete'
      phase: number
      phase_name: string
      cost_usd: number
    }
  | { kind: 'paused'; completed_phase: number; next_phase: number }
  | { kind: 'resumed'; next_phase: number }
  | { kind: 'run_complete'; total_cost_usd: number }
  | { kind: 'run_canceled' }
  | { kind: 'error'; error: string }

export type LogEntry = LogEntryInput & { id: number }

export interface UseRunReturn {
  status: RunStatus
  runId: string | null
  currentPhase: number | null
  /** When status === 'paused', the phase that just finished and
   * triggered the pause. Null otherwise. */
  pausedAfter: number | null
  /** When status === 'paused', the phase about to run next
   * once the user clicks Continue. Null otherwise. */
  nextPhase: number | null
  phaseUpdates: Map<number, PhaseUpdate>
  log: LogEntry[]
  cumulativeCost: number
  error: string | null
  /** Phase 1 exploration screenshots streamed via SSE (M1). */
  screenshots: { file: string; url: string }[]
  startRun: (req: RunRequest) => Promise<void>
  cancel: () => Promise<void>
  continueRun: () => Promise<void>
}

interface UseRunOptions {
  /** Fires once the POST /api/runs returns successfully and the SSE
   * stream is subscribed. Use this to refetch /api/project so the
   * phase rail reflects the backend's per-run state reset (phases in
   * the request were marked pending) before any phase_started event
   * arrives. */
  onStart?: () => void
  /** Fires when the run finishes — any terminal status (complete,
   * canceled, error). Typically used to refetch /api/project to
   * surface the persisted state.json metrics. */
  onComplete?: () => void
}

/**
 * Hook owning the lifecycle of a single multi-phase run. It POSTs
 * /api/runs, subscribes to the SSE event stream, and exposes the
 * accumulated state so the UI can animate phase pills, render live
 * agent text in the drawer, and tick the cost meter.
 */
export function useRun(options?: UseRunOptions): UseRunReturn {
  const { onStart, onComplete } = options ?? {}
  const [status, setStatus] = useState<RunStatus>('idle')
  const [runId, setRunId] = useState<string | null>(null)
  const [currentPhase, setCurrentPhase] = useState<number | null>(null)
  const [pausedAfter, setPausedAfter] = useState<number | null>(null)
  const [nextPhase, setNextPhase] = useState<number | null>(null)
  const [phaseUpdates, setPhaseUpdates] = useState<Map<number, PhaseUpdate>>(
    new Map(),
  )
  const [log, setLog] = useState<LogEntry[]>([])
  const [cumulativeCost, setCumulativeCost] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [screenshots, setScreenshots] = useState<
    { file: string; url: string }[]
  >([])

  const subscriptionRef = useRef<StreamSubscription | null>(null)
  const runIdRef = useRef<string | null>(null)
  const logIdRef = useRef(0)
  const onStartRef = useRef(onStart)
  const onCompleteRef = useRef(onComplete)

  useEffect(() => {
    onStartRef.current = onStart
  }, [onStart])

  useEffect(() => {
    onCompleteRef.current = onComplete
  }, [onComplete])

  const closeSubscription = () => {
    if (subscriptionRef.current) {
      subscriptionRef.current.close()
      subscriptionRef.current = null
    }
  }

  const appendLog = (entry: LogEntryInput) => {
    logIdRef.current += 1
    const id = logIdRef.current
    setLog((prev) => [...prev, { ...entry, id }])
  }

  const handleEvent = useCallback((event: RunEvent) => {
    switch (event.type) {
      case 'phase_started':
        setCurrentPhase(event.phase)
        setPhaseUpdates((prev) => {
          const next = new Map(prev)
          next.set(event.phase, { status: 'running' })
          return next
        })
        appendLog({
          kind: 'phase_started',
          phase: event.phase,
          phase_name: event.phase_name,
          ts: event.ts,
        })
        break

      case 'text_chunk':
        appendLog({
          kind: 'text',
          phase: phaseFromSessionId(event.session_id),
          text: event.text,
        })
        break

      case 'tool_use':
        appendLog({
          kind: 'tool_use',
          phase: phaseFromSessionId(event.session_id),
          tool: event.tool,
          arg: summarizeToolInput(event.tool, event.tool_input),
        })
        break

      case 'phase_complete':
        setPhaseUpdates((prev) => {
          const next = new Map(prev)
          next.set(event.phase, {
            status: 'complete',
            cost_usd: event.cost_usd,
            duration_ms: event.duration_ms,
            num_turns: event.num_turns,
          })
          return next
        })
        setCumulativeCost((prev) => prev + (event.cost_usd ?? 0))
        setCurrentPhase(null)
        appendLog({
          kind: 'phase_complete',
          phase: event.phase,
          phase_name: event.phase_name,
          cost_usd: event.cost_usd,
        })
        break

      case 'phase_error':
        setPhaseUpdates((prev) => {
          const next = new Map(prev)
          next.set(event.phase, { status: 'error', error: event.error })
          return next
        })
        appendLog({ kind: 'error', error: event.error })
        break

      case 'screenshot':
        // Phase 1 exploration shots (M1) — feed the filmstrip live.
        setScreenshots((prev) =>
          prev.some((s) => s.file === event.file)
            ? prev
            : [...prev, { file: event.file, url: event.url }],
        )
        break

      case 'paused':
        setStatus('paused')
        setPausedAfter(event.completed_phase)
        setNextPhase(event.next_phase)
        appendLog({
          kind: 'paused',
          completed_phase: event.completed_phase,
          next_phase: event.next_phase,
        })
        break

      case 'resumed':
        setStatus('running')
        setPausedAfter(null)
        setNextPhase(null)
        appendLog({ kind: 'resumed', next_phase: event.next_phase })
        break

      case 'run_complete':
        setStatus('complete')
        setCurrentPhase(null)
        setPausedAfter(null)
        setNextPhase(null)
        appendLog({ kind: 'run_complete', total_cost_usd: event.total_cost_usd })
        closeSubscription()
        onCompleteRef.current?.()
        break

      case 'run_canceled':
        setStatus('canceled')
        // Clear any still-running phase entries so the pill falls back
        // to whatever state.json says rather than staying stuck on a
        // spinner. mergePhases will re-derive from useProject().
        setPhaseUpdates((prev) => {
          const next = new Map(prev)
          for (const [num, update] of next) {
            if (update.status === 'running') {
              next.delete(num)
            }
          }
          return next
        })
        setCurrentPhase(null)
        setPausedAfter(null)
        setNextPhase(null)
        appendLog({ kind: 'run_canceled' })
        closeSubscription()
        onCompleteRef.current?.()
        break

      case 'run_error':
        setStatus('error')
        setError(event.error)
        // Same cleanup as cancel — don't leave any phase stuck on a
        // spinner if the run died mid-flight.
        setPhaseUpdates((prev) => {
          const next = new Map(prev)
          for (const [num, update] of next) {
            if (update.status === 'running') {
              next.delete(num)
            }
          }
          return next
        })
        setCurrentPhase(null)
        setPausedAfter(null)
        setNextPhase(null)
        appendLog({ kind: 'error', error: event.error })
        closeSubscription()
        onCompleteRef.current?.()
        break
    }
  }, [])

  const startRunImpl = useCallback(
    async (req: RunRequest) => {
      if (status === 'starting' || status === 'running') {
        throw new Error('a run is already in progress')
      }
      // Reset state for a new run.
      setStatus('starting')
      setError(null)
      setLog([])
      setPhaseUpdates(new Map())
      setCumulativeCost(0)
      setCurrentPhase(null)
      setPausedAfter(null)
      setNextPhase(null)
      setRunId(null)
      // Only clear the filmstrip when Phase 1 is about to re-explore
      // (the runner clears the exploration dir then too). A [2..6]
      // confirm run keeps the strip from the exploration run.
      if (req.phases.includes(1)) {
        setScreenshots([])
      }
      logIdRef.current = 0

      try {
        const info = await startRun(req)
        setRunId(info.run_id)
        runIdRef.current = info.run_id
        setStatus('running')
        // Backend reset state.json's phases for this run before
        // returning. Refetch project state so the rail reflects that
        // immediately (otherwise the user sees stale entries from a
        // prior run until the first phase_complete event lands).
        onStartRef.current?.()
        subscriptionRef.current = subscribeToRunStream(
          info.run_id,
          handleEvent,
          (err) => {
            // Log to console; rely on terminal events to close cleanly.
            console.error('Run stream error:', err)
          },
        )
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err)
        setStatus('error')
        setError(msg)
        throw err
      }
    },
    [status, handleEvent],
  )

  const cancel = useCallback(async () => {
    const id = runIdRef.current
    if (!id || (status !== 'running' && status !== 'paused')) return
    try {
      await cancelRun(id)
      // Status transitions via the run_canceled event from the stream.
    } catch (err) {
      console.error('Cancel failed:', err)
    }
  }, [status])

  const continueRunImpl = useCallback(async () => {
    const id = runIdRef.current
    if (!id || status !== 'paused') return
    try {
      await continueRun(id)
      // Status transitions via the resumed event from the stream.
    } catch (err) {
      console.error('Continue failed:', err)
    }
  }, [status])

  // Tear down the EventSource if the consumer unmounts mid-run.
  useEffect(() => {
    return () => {
      closeSubscription()
    }
  }, [])

  return {
    status,
    runId,
    currentPhase,
    pausedAfter,
    nextPhase,
    phaseUpdates,
    log,
    cumulativeCost,
    error,
    screenshots,
    startRun: startRunImpl,
    cancel,
    continueRun: continueRunImpl,
  }
}

function phaseFromSessionId(sessionId: string): number | null {
  // Session ids are "phaseN" (legacy) or "phaseN-<run8>" since #53.
  const match = /^phase(\d+)(?:-|$)/.exec(sessionId)
  if (!match || !match[1]) return null
  return parseInt(match[1], 10)
}

/**
 * Extract the most informative argument from a tool_use input dict
 * for display alongside the tool name in the drawer log. Returns null
 * when the tool is unknown or the expected field is missing — the row
 * falls back to just the tool name.
 */
function summarizeToolInput(tool: string, input: unknown): string | null {
  if (input === null || typeof input !== 'object') return null
  const o = input as Record<string, unknown>
  const pick = (key: string): string | null => {
    const v = o[key]
    return typeof v === 'string' && v.length > 0 ? v : null
  }
  let raw: string | null = null
  switch (tool) {
    case 'Bash':
      raw = pick('command')
      break
    case 'Read':
    case 'Write':
    case 'Edit':
    case 'NotebookEdit':
      raw = pick('file_path')
      break
    case 'Glob':
    case 'Grep':
      raw = pick('pattern')
      break
    case 'WebFetch':
    case 'WebSearch':
      raw = pick('url') ?? pick('query')
      break
    case 'TodoWrite': {
      const todos = o.todos
      if (Array.isArray(todos) && todos.length > 0) {
        const first = todos[0]
        if (first && typeof first === 'object') {
          const content = (first as Record<string, unknown>).content
          if (typeof content === 'string') raw = content
        }
      }
      break
    }
    default:
      raw = null
  }
  if (raw === null) return null
  const flat = raw.replace(/\s+/g, ' ').trim()
  return flat.length > 80 ? flat.slice(0, 77) + '…' : flat
}
