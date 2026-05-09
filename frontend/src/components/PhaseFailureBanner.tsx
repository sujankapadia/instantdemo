import { CircleX } from 'lucide-react'

interface PhaseFailureBannerProps {
  phaseNumber: number
  phaseName: string
  error: string
}

const PHASE_NAMES: Record<number, string> = {
  1: 'Analyze',
  2: 'Narrate',
  3: 'Gather',
  4: 'Script',
  5: 'Validate',
}

export function PhaseFailureBanner({
  phaseNumber,
  phaseName,
  error,
}: PhaseFailureBannerProps) {
  const label = phaseName || PHASE_NAMES[phaseNumber] || `Phase ${phaseNumber}`
  return (
    <div className="flex items-start gap-3 border-b border-destructive/40 bg-destructive/10 px-4 py-2 text-destructive">
      <CircleX className="mt-0.5 size-4 shrink-0" />
      <div className="space-y-1 text-sm">
        <p className="font-medium">
          Phase {phaseNumber} ({label}) failed
        </p>
        <p className="font-mono text-xs text-destructive/90">{error}</p>
        <p className="text-xs text-muted-foreground">
          Click the play button on the failed phase to re-run it, or
          inspect the agent log below for details.
        </p>
      </div>
    </div>
  )
}
