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
import { PhaseFailureBanner } from './PhaseFailureBanner'
import { RunInProgressBanner } from './RunInProgressBanner'
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
  // Editor pane (phase artifacts / JSON) is hidden by default — those
  // are developer-facing and text-heavy. The right pane (video +
  // segments) is the primary end-user surface. Toggle in the header
  // shows the editor; clicking a phase pill auto-opens it.
  const [editorVisible, setEditorVisible] = useState(false)

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
        editorVisible={editorVisible}
        onToggleEditor={() => setEditorVisible((v) => !v)}
      />
      {isError ? (
        <ErrorBanner message={state.error} onRetry={refetch} />
      ) : null}
      {run.status === 'idle' && data?.current_run_id ? (
        <RunInProgressBanner runId={data.current_run_id} />
      ) : null}
      {(() => {
        // Phase-specific failure banner takes precedence over the
        // generic run-error banner when we know which phase broke.
        if (run.status !== 'error') return null
        for (const [num, upd] of run.phaseUpdates) {
          if (upd.status === 'error') {
            return (
              <PhaseFailureBanner
                phaseNumber={num}
                phaseName={
                  ['Analyze', 'Narrate', 'Gather', 'Script', 'Validate'][
                    num - 1
                  ] ?? ''
                }
                error={upd.error ?? run.error ?? 'Unknown error'}
              />
            )
          }
        }
        return run.error ? (
          <ErrorBanner
            message={`Run failed: ${run.error}`}
            onRetry={() => {/* user re-runs via per-phase button */}}
          />
        ) : null
      })()}
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
        onSelect={(num) => {
          setSelected(num)
          // Auto-open the editor when the user explicitly clicks a
          // phase pill — they want to see that phase's content.
          if (!editorVisible) setEditorVisible(true)
        }}
        loading={isLoading}
        runStatus={run.status}
        currentPhase={run.currentPhase}
        onRunPhase={empty ? undefined : handleRunPhase}
      />
      {(() => {
        // Empty project? Always show the editor pane so the user sees
        // the onboarding message regardless of the toggle. Once they
        // start a project, the toggle controls visibility normally.
        const showEditor = editorVisible || empty
        return (
          <main className="flex min-h-0 flex-1">
            {showEditor ? (
              <div className="flex-[3] min-w-0">
                <EditorPane
                  phase={phase}
                  empty={empty}
                  projectDir={projectDir}
                />
              </div>
            ) : null}
            <div className={showEditor ? 'flex-[2] min-w-0' : 'flex-1 min-w-0'}>
              <RightPane runStatus={run.status} />
            </div>
          </main>
        )
      })()}
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
