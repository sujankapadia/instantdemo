import { X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ArtifactView } from './ArtifactView'
import { LogDrawer } from './LogDrawer'
import { PhaseRail, type PhaseInfo } from './PhaseRail'
import { Phase4TriagePanel } from './Phase4TriagePanel'
import { formatCostUsd } from '@/lib/format'
import type { ExploreFindings } from '@/api/project'
import type { LogEntry, RunStatus } from '@/hooks/useRun'

interface InspectorProps {
  open: boolean
  onClose: () => void
  phases: PhaseInfo[]
  selected: number
  onSelect: (num: number) => void
  runStatus: RunStatus
  currentPhase: number | null
  onRunPhase?: (num: number) => void
  log: LogEntry[]
  logOpen: boolean
  onLogOpenChange: (open: boolean) => void
  totalCostUsd: number
  pauseBetweenPhases: boolean
  onPauseChange: (value: boolean) => void
  /** Phase 4 BLOCKED triage (engineer-facing here; the storyboard's
   *  failure cards are the maker-facing surface). */
  triage?: { findings: ExploreFindings; onRegenerate: () => void } | null
  loading?: boolean
}

/**
 * The projection booth (DESIGN.md principle 4): every piece of
 * developer apparatus — phase rail, artifacts, agent log, costs,
 * run options — behind one deliberate threshold. Non-modal by
 * design: focus must not trap while a run streams on the stage.
 */
export function Inspector({
  open,
  onClose,
  phases,
  selected,
  onSelect,
  runStatus,
  currentPhase,
  onRunPhase,
  log,
  logOpen,
  onLogOpenChange,
  totalCostUsd,
  pauseBetweenPhases,
  onPauseChange,
  triage,
  loading,
}: InspectorProps) {
  if (!open) return null

  return (
    <aside
      className="fixed inset-y-0 right-0 z-40 flex w-[min(46vw,760px)] flex-col border-l border-border bg-background shadow-2xl"
      role="complementary"
      aria-label="Inspector"
    >
      <div className="flex h-10 shrink-0 items-center justify-between border-b border-border bg-muted/30 px-3">
        <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Inspector
        </span>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label="Close inspector"
          onClick={onClose}
        >
          <X className="size-4" />
        </Button>
      </div>

      <PhaseRail
        phases={phases}
        selected={selected}
        onSelect={onSelect}
        loading={loading}
        runStatus={runStatus}
        currentPhase={currentPhase}
        onRunPhase={onRunPhase}
      />

      {triage ? (
        <Phase4TriagePanel
          findings={triage.findings}
          onRegenerate={triage.onRegenerate}
          onViewReport={() => onSelect(4)}
        />
      ) : null}

      <div className="min-h-0 flex-1">
        <ArtifactView
          phase={
            phases.find((p) => p.num === selected) ?? phases[0]!
          }
        />
      </div>

      <LogDrawer
        log={log}
        status={runStatus}
        open={logOpen}
        onOpenChange={onLogOpenChange}
      />

      <div className="flex h-10 shrink-0 items-center justify-between border-t border-border bg-muted/30 px-3 text-xs">
        <label className="flex cursor-pointer items-center gap-2 text-muted-foreground">
          <input
            type="checkbox"
            checked={pauseBetweenPhases}
            onChange={(e) => onPauseChange(e.target.checked)}
            className="size-3.5 cursor-pointer"
          />
          Pause between phases
        </label>
        <span
          className="font-mono text-muted-foreground"
          aria-label="Total project cost"
        >
          {formatCostUsd(totalCostUsd)}
        </span>
      </div>
    </aside>
  )
}
