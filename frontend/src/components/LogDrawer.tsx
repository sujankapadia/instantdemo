import { useEffect, useRef, useState } from 'react'
import {
  Ban,
  CheckCircle2,
  ChevronUp,
  CircleX,
  Loader2,
  Pause,
  Play,
  Terminal,
  Wrench,
} from 'lucide-react'
import { Collapsible, CollapsibleContent } from '@/components/ui/collapsible'
import { cn } from '@/lib/utils'
import { formatCostUsd } from '@/lib/format'
import { phaseName } from '@/lib/phases'
import type { LogEntry, RunStatus } from '@/hooks/useRun'

interface LogDrawerProps {
  log: LogEntry[]
  status: RunStatus
  /** Optional controlled open state. When provided, the drawer
   *  becomes fully controlled by the parent (used for Esc → close
   *  everything). When omitted, the drawer manages its own state. */
  open?: boolean
  onOpenChange?: (open: boolean) => void
}

export function LogDrawer({
  log,
  status,
  open: controlledOpen,
  onOpenChange,
}: LogDrawerProps) {
  const [internalOpen, setInternalOpen] = useState(false)
  const open = controlledOpen ?? internalOpen
  const setOpen = (next: boolean | ((prev: boolean) => boolean)) => {
    const resolved =
      typeof next === 'function' ? (next as (p: boolean) => boolean)(open) : next
    if (onOpenChange) onOpenChange(resolved)
    if (controlledOpen === undefined) setInternalOpen(resolved)
  }
  const scrollRef = useRef<HTMLDivElement>(null)

  // Auto-open on run start lives in Layout (not here), gated on the
  // detailsVisible setting so end-user mode stays quiet during runs.
  // LogDrawer is now purely a controlled presentational component.

  // Auto-scroll to the bottom as new entries arrive.
  useEffect(() => {
    if (open && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [log, open])

  return (
    <Collapsible
      open={open}
      onOpenChange={setOpen}
      className="border-t border-border bg-background"
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex h-9 w-full items-center justify-between px-4 text-left text-xs font-medium uppercase tracking-wide text-muted-foreground hover:text-foreground cursor-pointer"
      >
        <span className="flex items-center gap-2">
          <Terminal className="size-3.5" />
          Agent log
          <RunStatusPip status={status} />
        </span>
        <ChevronUp
          className={cn(
            'size-4 transition-transform duration-200',
            open ? 'rotate-180' : '',
          )}
        />
      </button>
      <CollapsibleContent className="overflow-hidden">
        <div
          ref={scrollRef}
          className="h-64 overflow-auto border-t border-border p-4 font-mono text-xs"
        >
          {log.length === 0 ? (
            <p className="text-muted-foreground">
              Agent log will stream here during phase runs.
            </p>
          ) : (
            <LogBody log={log} />
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

function RunStatusPip({ status }: { status: RunStatus }) {
  if (status === 'running' || status === 'starting') {
    return (
      <span className="ml-1 flex items-center gap-1 text-sky-300">
        <Loader2 className="size-3 animate-spin" />
        Running
      </span>
    )
  }
  if (status === 'paused') {
    return (
      <span className="ml-1 flex items-center gap-1 text-amber-300">
        <Pause className="size-3" />
        Paused
      </span>
    )
  }
  if (status === 'complete') {
    return (
      <span className="ml-1 flex items-center gap-1 text-emerald-400">
        <CheckCircle2 className="size-3" />
        Complete
      </span>
    )
  }
  if (status === 'canceled') {
    return (
      <span className="ml-1 flex items-center gap-1 text-amber-400">
        <Ban className="size-3" />
        Canceled
      </span>
    )
  }
  if (status === 'error') {
    return (
      <span className="ml-1 flex items-center gap-1 text-destructive">
        <CircleX className="size-3" />
        Error
      </span>
    )
  }
  return null
}

function LogBody({ log }: { log: LogEntry[] }) {
  return (
    <div className="space-y-1">
      {log.map((entry) => (
        <LogRow key={entry.id} entry={entry} />
      ))}
    </div>
  )
}

function LogRow({ entry }: { entry: LogEntry }) {
  switch (entry.kind) {
    case 'phase_started':
      return (
        <div className="mt-3 flex items-center gap-2 border-t border-border pt-2 text-foreground first:mt-0 first:border-t-0 first:pt-0">
          <span className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
            Phase {entry.phase}
          </span>
          <span className="font-semibold">{phaseName(entry.phase)}</span>
        </div>
      )
    case 'text':
      return (
        <pre className="whitespace-pre-wrap text-foreground/90">
          {entry.text}
        </pre>
      )
    case 'tool_use':
      return (
        <div className="flex items-center gap-2 text-muted-foreground">
          <Wrench className="size-3" />
          <span className="text-[11px] uppercase tracking-wide">tool</span>
          <span className="font-medium text-foreground">{entry.tool}</span>
          {entry.arg ? (
            <span className="truncate font-mono text-xs text-muted-foreground/80">
              {entry.arg}
            </span>
          ) : null}
        </div>
      )
    case 'phase_complete':
      return (
        <div className="flex items-center gap-2 text-emerald-300">
          <CheckCircle2 className="size-3" />
          <span>
            Phase {entry.phase} ({phaseName(entry.phase)}) — {formatCostUsd(entry.cost_usd)}
          </span>
        </div>
      )
    case 'paused':
      return (
        <div className="mt-2 flex items-center gap-2 border-t border-border pt-2 text-amber-300">
          <Pause className="size-3" />
          <span>
            Paused after phase {entry.completed_phase} — waiting before phase{' '}
            {entry.next_phase}
          </span>
        </div>
      )
    case 'resumed':
      return (
        <div className="flex items-center gap-2 text-sky-300">
          <Play className="size-3" />
          <span>Resumed — running phase {entry.next_phase}</span>
        </div>
      )
    case 'run_complete':
      return (
        <div className="mt-2 border-t border-border pt-2 text-emerald-300">
          <span className="font-semibold">Run complete</span>
          <span className="ml-2 text-muted-foreground">
            total {formatCostUsd(entry.total_cost_usd)}
          </span>
        </div>
      )
    case 'run_canceled':
      return (
        <div className="mt-2 border-t border-border pt-2 text-amber-300">
          Run canceled
        </div>
      )
    case 'error':
      return (
        <div className="text-destructive">
          <span className="font-medium">Error: </span>
          {entry.error}
        </div>
      )
  }
}
