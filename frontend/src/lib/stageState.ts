// The one object's state machine: which face the Stage shows.
// Pure function so every surface decision lives in one place.

import type { ProjectState } from '@/api/project'
import type { RunStatus } from '@/hooks/useRun'

export type StageState =
  | 'empty'
  | 'exploring'
  | 'proposal'
  | 'storyboarding'
  | 'film'

export function deriveStage(args: {
  data: ProjectState | null
  runStatus: RunStatus
  currentPhase: number | null
  /** True the instant a cold start is submitted (before the first
   *  phase_started event) so the front door doesn't flash back. */
  pendingSetup: boolean
  storyboardExists: boolean
}): StageState {
  const { data, runStatus, currentPhase, pendingSetup, storyboardExists } =
    args
  const runActive = runStatus === 'starting' || runStatus === 'running'

  // A live run wins: the stage follows the camera.
  if (runActive) {
    if (currentPhase === 1) return 'exploring'
    if (currentPhase !== null && currentPhase >= 2) return 'storyboarding'
    // starting (no phase yet): cold start → exploring skeleton;
    // anything else keeps its persisted face below.
    if (pendingSetup || !data?.exists) return 'exploring'
  }

  if (!data?.exists) return 'empty'

  // Idle: persisted state decides (reload-safe — all predicates come
  // from /api/project, the M1/M2 pattern).
  const phase1 = data.phases?.['1']
  if (
    !data.intent_confirmed &&
    phase1?.status === 'completed' &&
    phase1?.intent_proposal
  ) {
    return 'proposal'
  }
  if (data.phases?.['6']?.status === 'completed') return 'film'
  if (storyboardExists) return 'storyboarding'
  // Project exists but no storyboard yet (e.g. paused after [1] with
  // intent already confirmed, or a partial legacy project): the film
  // face shows its "no film yet" placeholder.
  return 'film'
}
