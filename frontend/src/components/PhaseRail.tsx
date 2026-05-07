import { Check, Circle, CircleDashed, CircleX, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { formatCostUsd, formatDuration } from '@/lib/format'
import type { PhaseState, PhaseStatus } from '@/api/project'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'

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
}

interface PhaseRailProps {
  phases: PhaseInfo[]
  selected: number
  onSelect: (num: number) => void
  loading?: boolean
}

function StatusIcon({ status }: { status: PhaseStatus }) {
  const className = 'size-4 shrink-0'
  switch (status) {
    case 'completed':
      return <Check className={cn(className, 'text-emerald-400')} />
    case 'in_progress':
      return <Loader2 className={cn(className, 'animate-spin text-sky-400')} />
    case 'error':
      return <CircleX className={cn(className, 'text-destructive')} />
    case 'pending':
      return <CircleDashed className={cn(className, 'text-muted-foreground')} />
    default:
      return <Circle className={className} />
  }
}

function tooltipContent(phase: PhaseInfo): string | null {
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
  return null
}

export function PhaseRail({ phases, selected, onSelect, loading }: PhaseRailProps) {
  return (
    <nav className="flex h-12 items-center gap-1 border-b border-border bg-background px-3">
      {phases.map((phase) => {
        const isSelected = phase.num === selected
        const tip = tooltipContent(phase)

        const pill = (
          <button
            type="button"
            onClick={() => onSelect(phase.num)}
            disabled={loading}
            className={cn(
              'flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors cursor-pointer',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
              isSelected
                ? 'bg-secondary text-secondary-foreground'
                : 'text-muted-foreground hover:bg-secondary/50 hover:text-foreground',
              loading && 'opacity-60 cursor-default',
            )}
            aria-pressed={isSelected}
          >
            <StatusIcon status={phase.status} />
            <span className="text-muted-foreground">{phase.num}</span>
            <span>{phase.name}</span>
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
