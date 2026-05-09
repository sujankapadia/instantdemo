import { useCallback, useEffect, useState } from 'react'
import { Header } from './Header'
import {
  PhaseRail,
  buildPhaseInfos,
  mergePhases,
  PHASE_NUMBERS,
  type PhaseInfo,
} from './PhaseRail'
import { EditorPane } from './EditorPane'
import { RightPane } from './RightPane'
import { LogDrawer } from './LogDrawer'
import { ErrorBanner } from './ErrorBanner'
import { NewProjectModal } from './NewProjectModal'
import { PauseBanner } from './PauseBanner'
import { useProject } from '@/hooks/useProject'
import { useRun } from '@/hooks/useRun'

const LOADING_PHASES: PhaseInfo[] = PHASE_NUMBERS.map((num) => ({
  num,
  name: ['Analyze', 'Narrate', 'Gather', 'Script', 'Validate'][num - 1] ?? '',
  status: 'pending',
}))

export function Layout() {
  const { state, refetch } = useProject()
  const run = useRun({ onStart: refetch, onComplete: refetch })
  const [selected, setSelected] = useState<number>(1)
  const [newProjectOpen, setNewProjectOpen] = useState(false)

  const isLoading = state.status === 'loading'
  const isError = state.status === 'error'
  const data = state.status === 'success' ? state.data : null

  const basePhases = data ? buildPhaseInfos(data.phases) : LOADING_PHASES
  const phases = mergePhases(basePhases, run.phaseUpdates, run.currentPhase)
  const phase = phases.find((p) => p.num === selected) ?? phases[0]

  const projectName = data?.name ?? ''
  const projectDir = data?.project_dir
  const url = data?.url ?? null
  const empty = data ? !data.exists : false

  const handleRunPhase = useCallback(
    (phaseNum: number) => {
      if (!data || !data.url) {
        // Empty/loading project — nothing to point the agent at yet.
        return
      }
      void run.startRun({
        phases: [phaseNum],
        url: data.url,
        describe: data.describe ?? undefined,
      })
    },
    [data, run],
  )

  const handleNewProjectSubmit = useCallback(
    (values: {
      url: string
      describe: string
      tts: 'kokoro'
      pause_between_phases: boolean
    }) => {
      void run.startRun({
        phases: [1, 2, 3, 4, 5],
        url: values.url,
        describe: values.describe || undefined,
        tts: values.tts,
        pause_between_phases: values.pause_between_phases,
      })
    },
    [run],
  )

  // When the run pauses, auto-select the just-completed phase so the
  // user lands on the artifact they likely want to review. The hook's
  // pausedAfter is set when the paused event arrives and cleared on
  // resume / cancel, so this fires once per pause.
  useEffect(() => {
    if (run.status === 'paused' && run.pausedAfter !== null) {
      setSelected(run.pausedAfter)
    }
  }, [run.status, run.pausedAfter])

  return (
    <div className="flex h-screen flex-col bg-background text-foreground">
      <Header
        projectName={projectName}
        url={url}
        loading={isLoading}
        runStatus={run.status}
        cumulativeCost={run.cumulativeCost}
        onCancel={() => void run.cancel()}
        onNewProject={() => setNewProjectOpen(true)}
      />
      {isError ? (
        <ErrorBanner message={state.error} onRetry={refetch} />
      ) : null}
      {run.status === 'error' && run.error ? (
        <ErrorBanner
          message={`Run failed: ${run.error}`}
          onRetry={() => {/* user re-runs via per-phase button */}}
        />
      ) : null}
      {run.status === 'paused' ? (
        <PauseBanner
          completedPhase={run.pausedAfter}
          nextPhase={run.nextPhase}
          onContinue={() => void run.continueRun()}
        />
      ) : null}
      <PhaseRail
        phases={phases}
        selected={selected}
        onSelect={setSelected}
        loading={isLoading}
        runStatus={run.status}
        currentPhase={run.currentPhase}
        onRunPhase={empty ? undefined : handleRunPhase}
      />
      <main className="flex min-h-0 flex-1">
        <div className="flex-[3] min-w-0">
          <EditorPane phase={phase} empty={empty} projectDir={projectDir} />
        </div>
        <div className="flex-[2] min-w-0">
          <RightPane />
        </div>
      </main>
      <LogDrawer log={run.log} status={run.status} />
      <NewProjectModal
        open={newProjectOpen}
        onOpenChange={setNewProjectOpen}
        willOverwrite={data ? data.exists : false}
        defaultValues={{
          url: data?.url ?? '',
          describe: data?.describe ?? '',
        }}
        onSubmit={handleNewProjectSubmit}
      />
    </div>
  )
}
