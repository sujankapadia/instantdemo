import { Pause, Play } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PHASE_NAMES } from '@/lib/phases'

interface PauseBannerProps {
  completedPhase: number | null
  nextPhase: number | null
  onContinue: () => void
}

export function PauseBanner({
  completedPhase,
  nextPhase,
  onContinue,
}: PauseBannerProps) {
  const completedLabel =
    completedPhase !== null
      ? `Phase ${completedPhase} (${PHASE_NAMES[completedPhase] ?? ''})`
      : 'The previous phase'
  const nextLabel =
    nextPhase !== null
      ? `Phase ${nextPhase} (${PHASE_NAMES[nextPhase] ?? ''})`
      : 'the next phase'

  return (
    <div className="flex items-center justify-between gap-4 border-b border-amber-500/30 bg-amber-500/10 px-4 py-2 text-amber-200">
      <div className="flex items-center gap-2 text-sm">
        <Pause className="size-4 shrink-0" />
        <span>
          <strong>{completedLabel}</strong> completed. Review the artifact,
          then click Continue to run <strong>{nextLabel}</strong>.
        </span>
      </div>
      <Button size="sm" onClick={onContinue}>
        <Play className="size-3" />
        Continue
      </Button>
    </div>
  )
}
