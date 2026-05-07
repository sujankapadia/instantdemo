import { Check, Circle, CircleDashed, CircleX, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

export type PhaseStatus =
  | 'pending'
  | 'in_progress'
  | 'completed'
  | 'error'

export interface PhaseInfo {
  num: number
  name: string
  status: PhaseStatus
}

interface PhaseRailProps {
  phases: PhaseInfo[]
  selected: number
  onSelect: (num: number) => void
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

export function PhaseRail({ phases, selected, onSelect }: PhaseRailProps) {
  return (
    <nav className="flex h-12 items-center gap-1 border-b border-border bg-background px-3">
      {phases.map((phase) => {
        const isSelected = phase.num === selected
        return (
          <button
            key={phase.num}
            type="button"
            onClick={() => onSelect(phase.num)}
            className={cn(
              'flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors cursor-pointer',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
              isSelected
                ? 'bg-secondary text-secondary-foreground'
                : 'text-muted-foreground hover:bg-secondary/50 hover:text-foreground',
            )}
            aria-pressed={isSelected}
          >
            <StatusIcon status={phase.status} />
            <span className="text-muted-foreground">{phase.num}</span>
            <span>{phase.name}</span>
          </button>
        )
      })}
    </nav>
  )
}
