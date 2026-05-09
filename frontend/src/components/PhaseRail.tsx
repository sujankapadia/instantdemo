import { Ban, Check, Circle, CircleDashed, CircleX, Loader2, Play } from 'lucide-react'
import { cn } from '@/lib/utils'
import { formatCostUsd, formatDuration } from '@/lib/format'
import type { PhaseState, PhaseStatus } from '@/api/project'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import type { PhaseUpdate, RunStatus } from '@/hooks/useRun'

const PHASE_NAMES: Record<number, string> = {
  1: 'Analyze',
  2: 'Narrate',
  3: 'Gather',
  4: 'Script',
  5: 'Validate',
}

export const PHASE_NUMBERS = [1, 2, 3, 4, 5] as const

export interface PhaseInfo {
  num: number
  name: string
  status: PhaseStatus
  detail?: PhaseState
  /** True when an upstream phase ran more recently than this one. */
  stale?: boolean
}

interface PhaseRailProps {
  phases: PhaseInfo[]
  selected: number
  onSelect: (num: number) => void
  loading?: boolean
  runStatus: RunStatus
  currentPhase: number | null
  onRunPhase?: (phaseNum: number) => void
}

function StatusIcon({
  status,
  isCurrentlyRunning,
}: {
  status: PhaseStatus
  isCurrentlyRunning: boolean
}) {
  const className = 'size-4 shrink-0'
  if (isCurrentlyRunning) {
    return <Loader2 className={cn(className, 'animate-spin text-sky-400')} />
  }
  switch (status) {
    case 'completed':
      return <Check className={cn(className, 'text-emerald-400')} />
    case 'in_progress':
      return <Loader2 className={cn(className, 'animate-spin text-sky-400')} />
    case 'error':
      return <CircleX className={cn(className, 'text-destructive')} />
    case 'canceled':
      return <Ban className={cn(className, 'text-amber-400')} />
    case 'pending':
      return <CircleDashed className={cn(className, 'text-muted-foreground')} />
    default:
      return <Circle className={className} />
  }
}

function tooltipContent(phase: PhaseInfo, isCurrentlyRunning: boolean): string | null {
  if (isCurrentlyRunning) return 'Running…'
  if (phase.stale) {
    return 'Stale — upstream phase has run more recently. Click ▶ to re-run.'
  }
  const detail = phase.detail
  if (!detail) return null
  if (phase.status === 'completed') {
    const parts: string[] = []
    if (typeof detail.cost_usd === 'number') parts.push(formatCostUsd(detail.cost_usd))
    if (typeof detail.duration_ms === 'number') parts.push(formatDuration(detail.duration_ms))
    if (typeof detail.num_turns === 'number') parts.push(`${detail.num_turns} turn${detail.num_turns === 1 ? '' : 's'}`)
    return parts.length > 0 ? parts.join(' · ') : null
  }
  if (phase.status === 'in_progress') return 'Running…'
  if (phase.status === 'error') return 'Failed'
  if (phase.status === 'canceled') return 'Canceled'
  return null
}

export function PhaseRail({
  phases,
  selected,
  onSelect,
  loading,
  runStatus,
  currentPhase,
  onRunPhase,
}: PhaseRailProps) {
  const isRunActive =
    runStatus === 'running' ||
    runStatus === 'starting' ||
    runStatus === 'paused'

  return (
    <nav className="flex h-12 items-center gap-1 border-b border-border bg-background px-3">
      {phases.map((phase) => {
        const isSelected = phase.num === selected
        const isCurrentlyRunning = isRunActive && currentPhase === phase.num
        const tip = tooltipContent(phase, isCurrentlyRunning)

        const pill = (
          <button
            type="button"
            onClick={() => onSelect(phase.num)}
            disabled={loading}
            className={cn(
              'group flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors cursor-pointer relative',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
              isSelected
                ? 'bg-secondary text-secondary-foreground'
                : 'text-muted-foreground hover:bg-secondary/50 hover:text-foreground',
              loading && 'opacity-60 cursor-default',
              phase.stale && !isCurrentlyRunning && 'pr-2',
            )}
            aria-pressed={isSelected}
          >
            <StatusIcon status={phase.status} isCurrentlyRunning={isCurrentlyRunning} />
            <span className="text-muted-foreground">{phase.num}</span>
            <span>{phase.name}</span>
            {phase.stale && !isCurrentlyRunning ? (
              <span
                className="ml-1 size-1.5 rounded-full bg-amber-400"
                aria-label="Stale"
              />
            ) : null}
            {onRunPhase ? (
              <span
                role="button"
                tabIndex={0}
                aria-label={`Run phase ${phase.num}`}
                aria-disabled={isRunActive}
                onClick={(e) => {
                  e.stopPropagation()
                  if (isRunActive) return
                  onRunPhase(phase.num)
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    e.stopPropagation()
                    if (isRunActive) return
                    onRunPhase(phase.num)
                  }
                }}
                className={cn(
                  'ml-1 inline-flex size-5 items-center justify-center rounded text-muted-foreground/60 opacity-0 transition-opacity hover:bg-secondary hover:text-foreground group-hover:opacity-100',
                  isRunActive && 'pointer-events-none cursor-not-allowed group-hover:opacity-30',
                )}
              >
                <Play className="size-3" />
              </span>
            ) : null}
          </button>
        )

        if (!tip) return <span key={phase.num}>{pill}</span>

        return (
          <Tooltip key={phase.num}>
            <TooltipTrigger asChild>{pill}</TooltipTrigger>
            <TooltipContent side="bottom">{tip}</TooltipContent>
          </Tooltip>
        )
      })}
    </nav>
  )
}

export function buildPhaseInfos(
  apiPhases: Record<string, PhaseState>,
): PhaseInfo[] {
  return PHASE_NUMBERS.map((num) => {
    const detail = apiPhases[String(num)]
    return {
      num,
      name: PHASE_NAMES[num] ?? `Phase ${num}`,
      status: detail?.status ?? 'pending',
      detail,
    }
  })
}

/**
 * Merge run-derived phase updates onto the project's persisted phase state.
 * - Phases the run has touched override their status from the live updates.
 * - Phases downstream of the most-recently-run phase are flagged as stale
 *   (if they were previously completed) so the rail visually conveys
 *   "this is no longer aligned with what just ran upstream."
 */
export function mergePhases(
  base: PhaseInfo[],
  updates: Map<number, PhaseUpdate>,
  currentPhase: number | null,
): PhaseInfo[] {
  // Find the highest-numbered phase that has been (re-)run in the current
  // session. Anything strictly above it that was previously completed is
  // visually stale.
  let mostRecentTouchedPhase = currentPhase ?? -1
  for (const num of updates.keys()) {
    if (num > mostRecentTouchedPhase) mostRecentTouchedPhase = num
  }

  return base.map((phase) => {
    const update = updates.get(phase.num)
    let status: PhaseStatus = phase.status
    let detail = phase.detail
    let stale = false

    if (update) {
      if (update.status === 'running') status = 'in_progress'
      else if (update.status === 'complete') {
        status = 'completed'
        if (typeof update.cost_usd === 'number') {
          detail = {
            ...phase.detail,
            cost_usd: update.cost_usd,
            duration_ms: update.duration_ms ?? phase.detail?.duration_ms,
            num_turns: update.num_turns ?? phase.detail?.num_turns,
          }
        }
      } else if (update.status === 'error') status = 'error'
    } else if (
      mostRecentTouchedPhase > 0 &&
      phase.num > mostRecentTouchedPhase &&
      phase.status === 'completed'
    ) {
      stale = true
    }

    return { ...phase, status, detail, stale }
  })
}
