import { CircleX } from 'lucide-react'
import { STAGE_FAILED_WHILE } from '@/lib/labels'

interface PhaseFailureBannerProps {
  phaseNumber: number
  error: string
  /** True when the error message points at a phase artifact file
   *  on disk — switches the helper line to direct the user to the
   *  open artifact rather than to a filesystem path. */
  artifactShown?: boolean
}

export function PhaseFailureBanner({
  phaseNumber,
  error,
  artifactShown,
}: PhaseFailureBannerProps) {
  const when = STAGE_FAILED_WHILE[phaseNumber] ?? 'working on your demo'
  // Strip the "See /path/to/phaseN.md for the full report" trailer —
  // when the artifact pane is open below, the path is redundant noise.
  const cleanedError = artifactShown
    ? error.replace(/\s*See [/\w.\-]+phase\d+\.md for the full report\.?\s*$/i, '').trim()
    : error
  return (
    <div className="flex items-start gap-3 border-b border-destructive/40 bg-destructive/10 px-4 py-2 text-destructive">
      <CircleX className="mt-0.5 size-4 shrink-0" />
      <div className="space-y-1 text-sm">
        <p className="font-medium">Something went wrong while {when}.</p>
        <p className="font-mono text-xs text-destructive/90">{cleanedError}</p>
        <p className="text-xs text-muted-foreground">
          {artifactShown
            ? 'The full diagnostic and recommended fix are in the report below.'
            : 'The full diagnostic is in the agent log; re-run the failed step from the phase rail.'}
        </p>
      </div>
    </div>
  )
}
