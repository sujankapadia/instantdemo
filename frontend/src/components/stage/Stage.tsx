import { AnimatePresence, LayoutGroup, motion } from 'motion/react'
import { StageEmpty } from './StageEmpty'
import { StageExploring } from './StageExploring'
import { StageProposal } from './StageProposal'
import { StageFilm } from './StageFilm'
import { StoryboardView } from '../StoryboardView'
import { deriveStage } from '@/lib/stageState'
import { FACE_TRANSITION, FACE_VARIANTS } from '@/lib/motion'
import type { ProjectState } from '@/api/project'
import type { Intent } from '@/api/runs'
import type { NewProjectInputs } from '../NewProjectForm'
import type { StoryboardFetchState } from '@/hooks/useStoryboard'
import type { RunStatus } from '@/hooks/useRun'

interface StageProps {
  data: ProjectState | null
  runStatus: RunStatus
  currentPhase: number | null
  pendingSetup: NewProjectInputs | null
  screenshots: { file: string; url: string }[]
  storyboard: StoryboardFetchState
  storyboardRefetch: () => void
  runCompleteToken: number
  gateOpen: boolean
  projectDir?: string | null
  onColdStart: (values: NewProjectInputs) => void
  onConfirmIntent: (intent: Intent) => void
  onApprove: () => void
  onRegenerate: () => void
  /** Lights-down signal from the film face. */
  onPlayingChange?: (playing: boolean) => void
}

/**
 * THE one object (DESIGN.md principle 2): a single center surface
 * that matures — front door → exploration filmstrip → proposal →
 * storyboard → the film. Every face is derived from server state
 * (deriveStage), so reloads land mid-journey correctly.
 */
export function Stage(props: StageProps) {
  const {
    data,
    runStatus,
    currentPhase,
    pendingSetup,
    screenshots,
    storyboard,
    storyboardRefetch,
    runCompleteToken,
    gateOpen,
    projectDir,
    onColdStart,
    onConfirmIntent,
    onApprove,
    onRegenerate,
  } = props

  const storyboardExists =
    storyboard.status === 'success' && storyboard.data.exists
  const stage = deriveStage({
    data,
    runStatus,
    currentPhase,
    pendingSetup: pendingSetup !== null,
    storyboardExists,
  })

  const face = (() => {
    switch (stage) {
      case 'empty':
        return (
          <StageEmpty
            projectDir={projectDir}
            submitting={runStatus === 'starting'}
            onSubmit={onColdStart}
          />
        )
      case 'exploring':
        return (
          <StageExploring
            screenshots={screenshots}
            exploring={runStatus === 'starting' || runStatus === 'running'}
          />
        )
      case 'proposal': {
        const phase1 = data?.phases?.['1']
        if (!phase1?.intent_proposal) return null
        return (
          <StageProposal
            proposal={phase1.intent_proposal as Intent}
            userIntent={pendingSetup?.intent ?? data?.intent ?? null}
            screens={phase1.screens}
            warnings={phase1.warnings}
            onConfirm={onConfirmIntent}
          />
        )
      }
      case 'storyboarding':
        return (
          <StoryboardView
            state={storyboard}
            refetch={storyboardRefetch}
            runStatus={runStatus}
            currentPhase={currentPhase}
            gateOpen={gateOpen}
            liveShots={screenshots}
            onApprove={onApprove}
            onRegenerate={onRegenerate}
            approving={
              (runStatus === 'starting' || runStatus === 'running') &&
              currentPhase !== null &&
              currentPhase >= 5
            }
          />
        )
      case 'film':
        return (
          <StageFilm
            runStatus={runStatus}
            runCompleteToken={runCompleteToken}
            onPlayingChange={props.onPlayingChange}
          />
        )
    }
  })()

  // One object, continuously transforming (motion budget item 1):
  // faces crossfade with a slight rise; the LayoutGroup lets the
  // exploration-frames container persist into the storyboard.
  return (
    <LayoutGroup>
      <AnimatePresence mode="wait">
        <motion.div
          key={stage}
          className="flex h-full w-full min-h-0 flex-1 flex-col"
          variants={FACE_VARIANTS}
          initial="initial"
          animate="animate"
          exit="exit"
          transition={FACE_TRANSITION}
        >
          {face}
        </motion.div>
      </AnimatePresence>
    </LayoutGroup>
  )
}
