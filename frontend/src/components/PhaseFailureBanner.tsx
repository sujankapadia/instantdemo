import { CircleX } from 'lucide-react'
import { PHASE_NAMES } from '@/lib/phases'

interface PhaseFailureBannerProps {
  phaseNumber: number
  phaseName: string
  error: string
  /** True when the error message points at a phase artifact file
   *  on disk — switches the helper line to direct the user to the
   *  open artifact rather than to a filesystem path. */
  artifactShown?: boolean
}

export function PhaseFailureBanner({
  phaseNumber,
  phaseName,
  error,
  artifactShown,
}: PhaseFailureBannerProps) {
  const label = phaseName || PHASE_NAMES[phaseNumber] || `Phase ${phaseNumber}`
  // Strip the "See /path/to/phaseN.md for the full report" trailer —
  // when the artifact pane is open below, the path is redundant noise.
  const cleanedError = artifactShown
    ? error.replace(/\s*See [/\w.\-]+phase\d+\.md for the full report\.?\s*$/i, '').trim()
    : error
  return (
    <div className="flex items-start gap-3 border-b border-destructive/40 bg-destructive/10 px-4 py-2 text-destructive">
      <CircleX className="mt-0.5 size-4 shrink-0" />
      <div className="space-y-1 text-sm">
        <p className="font-medium">
          Phase {phaseNumber} ({label}) failed
        </p>
        <p className="font-mono text-xs text-destructive/90">{cleanedError}</p>
        <p className="text-xs text-muted-foreground">
          {artifactShown
            ? `See the ${label} report below for the full diagnostic and recommended fix.`
            : 'Click the play button on the failed phase to re-run it, or inspect the agent log below for details.'}
        </p>
      </div>
    </div>
  )
}
