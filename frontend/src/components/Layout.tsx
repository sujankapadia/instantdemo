import { useCallback, useEffect, useRef, useState } from 'react'
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
import type { NewProjectInputs } from './NewProjectForm'
import { emptyIntent } from '@/api/runs'
import { PauseBanner } from './PauseBanner'
import { PhaseFailureBanner } from './PhaseFailureBanner'
import { Phase4TriagePanel } from './Phase4TriagePanel'
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
  // Bumped each time a run terminates — RightPane watches this to know
  // when to refresh segments + video. Cleaner than RightPane trying to
  // detect the transition itself.
  const [runCompleteToken, setRunCompleteToken] = useState(0)
  const run = useRun({
    onStart: refetch,
    onComplete: () => {
      refetch()
      setRunCompleteToken((t) => t + 1)
    },
  })
  const [selected, setSelected] = useState<number>(1)
  const [newProjectOpen, setNewProjectOpen] = useState(false)
  // Developer-facing details (phase rail + editor pane with phase
  // artifacts) are hidden by default — they're text-heavy and foreign
  // to typical end users. The right pane (video + segments) is the
  // primary surface. Toggle in the header reveals both; the phase
  // rail also auto-shows during an active run so users can watch
  // per-phase progress without finding the toggle.
  const [detailsVisible, setDetailsVisible] = useState(false)
  // Log drawer's open state is hoisted to Layout. Auto-opening on
  // run start lives here (was in LogDrawer), gated on detailsVisible
  // so end-user mode (details off) stays quiet during runs.
  const [logOpen, setLogOpen] = useState(false)
  const wasRunningRef = useRef(false)

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
    (values: NewProjectInputs) => {
      void run.startRun({
        phases: [1, 2, 3, 4, 5, 6],
        url: values.url,
        // Goal doubles as the legacy describe field so backend
        // synthesize-from-describe fallback keeps working when
        // older Pydantic models / tests look for describe.
        describe: values.intent.goal || undefined,
        source: values.source || undefined,
        intent: values.intent,
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
  // for RENDER_BLOCKED in Phase 6, which contains the minimum-fix
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

  // Auto-open the agent log drawer when a run starts — but only in
  // power-user mode (details visible). End-user mode stays quiet
  // during runs; progress is surfaced via the compact header
  // indicator instead. (Moved from LogDrawer's internal useEffect
  // so the gating lives next to the detailsVisible state.)
  useEffect(() => {
    const isRunning = run.status === 'starting' || run.status === 'running'
    if (isRunning && !wasRunningRef.current && detailsVisible) {
      setLogOpen(true)
    }
    wasRunningRef.current = isRunning
  }, [run.status, detailsVisible])

  // Esc → "clean view": collapse phase rail + editor + agent log
  // drawer in one keystroke. Skip when an input is focused (the user
  // is probably trying to cancel an edit, e.g. the inline segment
  // editor) and when a modal is open (Dialog/AlertDialog handle Esc
  // for themselves to close themselves).
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      const target = e.target as HTMLElement | null
      if (
        target &&
        (target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.isContentEditable)
      ) {
        return
      }
      if (document.querySelector('[role="dialog"][data-state="open"]')) {
        return
      }
      setDetailsVisible(false)
      setLogOpen(false)
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  return (
    <div className="flex h-screen flex-col bg-background text-foreground">
      <Header
        projectName={projectName}
        url={url}
        loading={isLoading}
        runStatus={run.status}
        currentPhase={run.currentPhase}
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
        // Suppress the banner for Phase 4 when the structured triage
        // panel is going to render below — the panel is a better,
        // humanized surface for the same error. See issue #48.
        if (run.status !== 'error') return null
        const phase4Triage =
          data?.phases?.['4']?.explore_overall === 'BLOCKED'
        for (const [num, upd] of run.phaseUpdates) {
          if (upd.status === 'error') {
            if (num === 4 && phase4Triage) {
              // Triage panel handles it — don't double-stack.
              return null
            }
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
        // Phase 4 triage panel — only when Phase 4 produced blocking
        // findings (FAIL_SELECTOR or FAIL_NARRATIVE on any segment).
        // See issue #48.
        const phase4 = data?.phases?.['4']
        const findings = phase4?.explore_findings
        if (!findings || phase4?.explore_overall !== 'BLOCKED') {
          return null
        }
        return (
          <Phase4TriagePanel
            findings={findings}
            onRegenerate={() => setNewProjectOpen(true)}
            onViewReport={() => {
              setSelected(4)
              setDetailsVisible(true)
            }}
          />
        )
      })()}
      {(() => {
        // Phase rail shows only when details is on. During end-user
        // runs (details off), progress is surfaced via the compact
        // header indicator instead. Power users (details on) still
        // see the rail throughout the run.
        if (!detailsVisible) return null
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
              <RightPane
                runStatus={run.status}
                runCompleteToken={runCompleteToken}
              />
            </div>
          </main>
        )
      })()}
      <LogDrawer
        log={run.log}
        status={run.status}
        open={logOpen}
        onOpenChange={setLogOpen}
      />
      <NewProjectModal
        open={newProjectOpen}
        onOpenChange={setNewProjectOpen}
        willOverwrite={data ? data.exists : false}
        // Title flips to "Regenerate demo" once a project exists, so
        // the same modal serves both cold-start and full-pipeline
        // regeneration. Per the design discussion: "Regenerate" is
        // the primary cascade affordance for end users.
        title={data?.exists ? 'Regenerate demo' : 'New project'}
        defaultValues={{
          url: data?.url ?? '',
          source: data?.source ?? '',
          // Prefill the full intent from /api/project (loaded from
          // intent.json or synthesized from describe). Lets a user
          // edit just one field (tone, focus) and regenerate.
          intent: data?.intent ?? {
            ...emptyIntent(),
            goal: data?.describe ?? '',
          },
        }}
        onSubmit={handleNewProjectSubmit}
      />
    </div>
  )
}
