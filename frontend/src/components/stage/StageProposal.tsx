import { IntentConfirmCard } from '../IntentConfirmCard'
import type { Intent } from '@/api/runs'
import type { ScreenInfo } from '@/api/project'

/**
 * The studio speaks (DESIGN.md principle 13): exploration concluded,
 * the proposal is the stage — centered, in the speaking register,
 * with the structured readback for refinement.
 */
export function StageProposal({
  proposal,
  userIntent,
  screens,
  warnings,
  onConfirm,
}: {
  proposal: Intent
  userIntent: Intent | null
  screens?: ScreenInfo[] | null
  warnings?: string[] | null
  onConfirm: (intent: Intent) => void
}) {
  return (
    <div className="flex h-full w-full flex-1 items-start justify-center overflow-y-auto">
      <div className="w-full max-w-2xl py-8">
        <IntentConfirmCard
          proposal={proposal}
          userIntent={userIntent}
          screens={screens}
          warnings={warnings}
          busy={false}
          onConfirm={onConfirm}
        />
      </div>
    </div>
  )
}
