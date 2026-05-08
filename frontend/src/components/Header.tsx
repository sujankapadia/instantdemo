import { Settings, Square } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { formatCostUsd } from '@/lib/format'
import type { RunStatus } from '@/hooks/useRun'

interface HeaderProps {
  projectName: string
  url?: string | null
  loading?: boolean
  runStatus: RunStatus
  cumulativeCost: number
  onCancel: () => void
}

export function Header({
  projectName,
  url,
  loading,
  runStatus,
  cumulativeCost,
  onCancel,
}: HeaderProps) {
  const isRunning = runStatus === 'running' || runStatus === 'starting'
  const showCost =
    runStatus !== 'idle' && (cumulativeCost > 0 || isRunning)

  return (
    <header className="flex h-14 items-center justify-between border-b border-border bg-background px-4">
      <div className="flex items-baseline gap-3">
        <span className="text-base font-semibold">InstantDemo</span>
        {loading ? (
          <span className="text-sm text-muted-foreground">Loading…</span>
        ) : (
          <>
            <span className="text-sm text-muted-foreground">{projectName}</span>
            {url ? (
              <span className="text-xs text-muted-foreground/70">{url}</span>
            ) : null}
          </>
        )}
      </div>
      <div className="flex items-center gap-2">
        {showCost ? (
          <span
            className={cn(
              'rounded-md border border-border bg-secondary/40 px-2 py-1 font-mono text-xs',
              isRunning ? 'text-foreground' : 'text-muted-foreground',
            )}
            aria-label="Cumulative run cost"
          >
            {formatCostUsd(cumulativeCost)}
          </span>
        ) : null}
        {isRunning ? (
          <Button
            size="sm"
            variant="destructive"
            onClick={onCancel}
            aria-label="Stop run"
          >
            <Square className="size-3" />
            Stop
          </Button>
        ) : null}
        <Button variant="ghost" size="icon" aria-label="Settings">
          <Settings />
        </Button>
      </div>
    </header>
  )
}
