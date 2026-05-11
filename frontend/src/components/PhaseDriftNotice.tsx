import { Info } from 'lucide-react'
import { PHASE_NAMES } from '@/lib/phases'

interface PhaseDriftNoticeProps {
  phaseNumber: number
}

/**
 * Shown on Phase 2 (Narrate) and Phase 3 (Gather) markdown artifacts
 * to clarify that those documents are the agent's draft plan from a
 * fixed moment in time, and don't reflect later per-segment edits made
 * through the segments list. The script (Phase 4) and rendered video
 * are the source of truth for what's actually playing.
 */
export function PhaseDriftNotice({ phaseNumber }: PhaseDriftNoticeProps) {
  const name = PHASE_NAMES[phaseNumber] ?? `Phase ${phaseNumber}`
  return (
    <div className="flex items-start gap-3 border-b border-sky-500/20 bg-sky-500/5 px-6 py-3 text-sm text-muted-foreground">
      <Info className="mt-0.5 size-4 shrink-0 text-sky-400" />
      <div className="space-y-1">
        <p>
          This is the agent's plan from Phase {phaseNumber} ({name}). It's
          a snapshot from when the phase last ran.
        </p>
        <p>
          Per-segment narration edits made in the segments list write
          directly to the script (Phase 4) and don't sync back here. To
          regenerate this plan, re-run Phase {phaseNumber}.
        </p>
      </div>
    </div>
  )
}
