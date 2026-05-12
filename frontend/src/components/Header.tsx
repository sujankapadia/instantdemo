import { PanelLeftClose, PanelLeftOpen, RefreshCw, Settings, Square } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
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
  onNewProject: () => void
  /** Hide the "New project" button when the empty-state CTA is the
   *  primary entry point (no project yet). */
  showNewProject?: boolean
  editorVisible: boolean
  onToggleEditor: () => void
}

export function Header({
  projectName,
  url,
  loading,
  runStatus,
  cumulativeCost,
  onCancel,
  onNewProject,
  showNewProject = true,
  editorVisible,
  onToggleEditor,
}: HeaderProps) {
  const isActive =
    runStatus === 'running' ||
    runStatus === 'starting' ||
    runStatus === 'paused'
  const showCost =
    runStatus !== 'idle' && (cumulativeCost > 0 || isActive)

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
              isActive ? 'text-foreground' : 'text-muted-foreground',
            )}
            aria-label="Cumulative run cost"
          >
            {formatCostUsd(cumulativeCost)}
          </span>
        ) : null}
        {isActive ? (
          <Button
            size="sm"
            variant="destructive"
            onClick={onCancel}
            aria-label="Stop run"
          >
            <Square className="size-3" />
            Stop
          </Button>
        ) : showNewProject ? (
          // When a project exists, this button opens the same modal as
          // "Get started" but with current intent values prefilled,
          // so users can tweak tone / focus / etc. and re-run the full
          // pipeline. Labeled "Regenerate" to match the user mental
          // model. The empty-state CTA ("Get started") covers cold-
          // start; this never shows on empty.
          <Button
            size="sm"
            variant="secondary"
            onClick={onNewProject}
            disabled={loading}
          >
            <RefreshCw className="size-3" />
            Regenerate
          </Button>
        ) : null}
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              aria-label={editorVisible ? 'Hide phase details' : 'Show phase details'}
              onClick={onToggleEditor}
            >
              {editorVisible ? <PanelLeftClose /> : <PanelLeftOpen />}
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            {editorVisible ? 'Hide phase details' : 'Show phase details'}
          </TooltipContent>
        </Tooltip>
        <Button variant="ghost" size="icon" aria-label="Settings">
          <Settings />
        </Button>
      </div>
    </header>
  )
}
