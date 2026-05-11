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
import { PHASE_NAMES_ORDERED, phaseName } from '@/lib/phases'

const LOADING_PHASES: PhaseInfo[] = PHASE_NUMBERS.map((num) => ({
  num,
  name: PHASE_NAMES_ORDERED[num - 1] ?? '',
  status: 'pending',
}))

export function Layout() {
  const { state, refetch } = useProject()
  const run = useRun({ onStart: refetch, onComplete: refetch })
  const [selected, setSelected] = useState<number>(1)
  const [newProjectOpen, setNewProjectOpen] = useState(false)
  // Developer-facing details (phase rail + editor pane with phase
  // artifacts) are hidden by default — they're text-heavy and foreign
  // to typical end users. The right pane (video + segments) is the
  // primary surface. Toggle in the header reveals both; the phase
  // rail also auto-shows during an active run so users can watch
  // per-phase progress without finding the toggle.
  const [detailsVisible, setDetailsVisible] = useState(false)

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
      source: string
      tts: 'kokoro'
      pause_between_phases: boolean
    }) => {
      void run.startRun({
        phases: [1, 2, 3, 4, 5],
        url: values.url,
        describe: values.describe || undefined,
        source: values.source || undefined,
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

  // When a phase errors, open the details pane and select that phase
  // so the user lands on the diagnostic report (especially important
  // for RENDER_BLOCKED in Phase 5, which contains the minimum-fix
  // recommendation). See #29.
  useEffect(() => {
    if (run.status !== 'error') return
    for (const [num, upd] of run.phaseUpdates) {
      if (upd.status === 'error') {
        setSelected(num)
        setDetailsVisible(true)
        break
      }
    }
  }, [run.status, run.phaseUpdates])

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
        showNewProject={!empty}
        editorVisible={detailsVisible}
        onToggleEditor={() => setDetailsVisible((v) => !v)}
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
                phaseName={phaseName(num)}
                error={upd.error ?? run.error ?? 'Unknown error'}
                artifactShown={detailsVisible && selected === num}
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
      {(() => {
        // Show the phase rail when the user opens details OR when a
        // run is in flight (so they can watch per-phase progress
        // without finding the toggle). Hide for idle end-user view.
        const isRunActive =
          run.status === 'running' ||
          run.status === 'starting' ||
          run.status === 'paused'
        const showPhaseRail = detailsVisible || isRunActive
        if (!showPhaseRail) return null
        return (
          <PhaseRail
            phases={phases}
            selected={selected}
            onSelect={(num) => {
              setSelected(num)
              // Clicking a phase pill is an explicit "I want details"
              // — open the editor pane so they can see the artifact.
              if (!detailsVisible) setDetailsVisible(true)
            }}
            loading={isLoading}
            runStatus={run.status}
            currentPhase={run.currentPhase}
            onRunPhase={empty ? undefined : handleRunPhase}
          />
        )
      })()}
      {(() => {
        // Empty project? Always show the editor pane so the user sees
        // the onboarding message regardless of the toggle. Once they
        // start a project, the toggle controls visibility normally.
        const showEditor = detailsVisible || empty
        return (
          <main className="flex min-h-0 flex-1">
            {showEditor ? (
              <div className="flex-[3] min-w-0">
                <EditorPane
                  phase={phase}
                  empty={empty}
                  projectDir={projectDir}
                  onNewProject={() => setNewProjectOpen(true)}
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
