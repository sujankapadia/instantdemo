import { Pause, Play } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { STAGE_DONE, STAGE_SENTENCES } from '@/lib/labels'

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
      ? `Paused after ${STAGE_DONE[completedPhase] ?? 'the last step'}.`
      : 'Paused.'
  const nextLabel =
    nextPhase !== null
      ? (STAGE_SENTENCES[nextPhase] ?? 'the next step').replace('…', '')
      : 'the next step'

  return (
    <div className="flex items-center justify-between gap-4 border-b border-status-warn/30 bg-status-warn/10 px-4 py-2 text-status-warn">
      <div className="flex items-center gap-2 text-sm">
        <Pause className="size-4 shrink-0" />
        <span>
          {completedLabel} Take a look, then continue with{' '}
          <strong>{nextLabel.toLowerCase()}</strong>.
        </span>
      </div>
      <Button size="sm" onClick={onContinue}>
        <Play className="size-3" />
        Continue
      </Button>
    </div>
  )
}
