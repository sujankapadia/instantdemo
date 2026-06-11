import { useCallback, useEffect, useRef, useState } from 'react'
import { Header } from './Header'
import {
  buildPhaseInfos,
  mergePhases,
  PHASE_NUMBERS,
  type PhaseInfo,
} from './PhaseRail'
import { Inspector } from './Inspector'
import { RightPane } from './RightPane'
import { ErrorBanner } from './ErrorBanner'
import { NewProjectModal } from './NewProjectModal'
import type { NewProjectInputs } from './NewProjectForm'
import { emptyIntent } from '@/api/runs'
import { PauseBanner } from './PauseBanner'
import { PhaseFailureBanner } from './PhaseFailureBanner'
import { IntentConfirmCard } from './IntentConfirmCard'
import { StageEmpty } from './stage/StageEmpty'
import { StoryboardView } from './StoryboardView'
import { useStoryboard } from '@/hooks/useStoryboard'
import { VoiceDialog } from './VoiceDialog'
import { useVoice } from '@/hooks/useVoice'
import { RunInProgressBanner } from './RunInProgressBanner'
import { useProject } from '@/hooks/useProject'
import { useRun } from '@/hooks/useRun'
import { PHASE_NAMES_ORDERED } from '@/lib/phases'

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
  const storyboard = useStoryboard()
  const storyboardRefetch = storyboard.refetch
  const run = useRun({
    onStart: () => {
      refetch()
      storyboardRefetch()
    },
    onComplete: () => {
      refetch()
      storyboardRefetch()
      setRunCompleteToken((t) => t + 1)
    },
    // Live storyboard during the [2,3,4] leg: scenes appear after
    // phase 2, selectors after 3, verification + thumbnails after 4.
    onPhaseComplete: (phase) => {
      if (phase >= 2 && phase <= 4) storyboardRefetch()
    },
  })
  const [selected, setSelected] = useState<number>(1)
  const [newProjectOpen, setNewProjectOpen] = useState(false)
  // Voice & Pronunciation dialog (M3) — header gear.
  const [voiceOpen, setVoiceOpen] = useState(false)
  const voice = useVoice()
  // Cold-start two-run flow (M1): form values stashed between the
  // exploration run [1] and the confirm run [2..6]. Falls back to
  // /api/project values after a reload.
  const [pendingSetup, setPendingSetup] = useState<NewProjectInputs | null>(
    null,
  )
  // The Inspector (one-object pass, DESIGN.md principle 4): ALL
  // developer apparatus — phase rail, artifacts, agent log, costs,
  // pause toggle — behind one deliberate threshold. There is no
  // details "mode" anymore; the default window has zero machinery.
  const [inspectorOpen, setInspectorOpen] = useState(false)
  // Log drawer's open state (the drawer now lives inside the
  // Inspector). Auto-opens on run start only when the inspector is
  // already open.
  const [logOpen, setLogOpen] = useState(false)
  // Pause-between-phases lives in the Inspector footer (relocated
  // from the cold-start form); applies to the next confirm/approve
  // runs started from the stage.
  const [pausePreference, setPausePreference] = useState(false)
  const wasRunningRef = useRef(false)

  const isLoading = state.status === 'loading'
  const isError = state.status === 'error'
  const data = state.status === 'success' ? state.data : null

  const basePhases = data ? buildPhaseInfos(data.phases) : LOADING_PHASES
  const phases = mergePhases(basePhases, run.phaseUpdates, run.currentPhase)

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
      const common = {
        url: values.url,
        // Goal doubles as the legacy describe field so backend
        // synthesize-from-describe fallback keeps working when
        // older Pydantic models / tests look for describe.
        describe: values.intent.goal || undefined,
        source: values.source || undefined,
        intent: values.intent,
        docs: values.docs || undefined,
        // No tts field since M3 — the renderer reads the project's
        // tts.json (edited via the Voice dialog).
        pause_between_phases: values.pause_between_phases,
      }
      if (data?.exists) {
        // Regenerate: intent is already curated — full single run.
        void run.startRun({ phases: [1, 2, 3, 4, 5, 6], ...common })
        return
      }
      // Cold start (M1 two-run flow): explore first; phases 2-6 run
      // after the user confirms the proposed intent. Stash the form
      // values so the confirm step can reuse url/source/tts.
      setPendingSetup(values)
      void run.startRun({ phases: [1], ...common })
    },
    [data, run],
  )

  const handleIntentConfirm = useCallback(
    (intent: import('@/api/runs').Intent) => {
      const url = pendingSetup?.url || data?.url
      if (!url) return
      // M2: the confirm run stops after the rehearsal — rendering
      // waits for storyboard approval (the gate).
      void run.startRun({
        phases: [2, 3, 4],
        url,
        describe: intent.goal || undefined,
        source: pendingSetup?.source || data?.source || undefined,
        intent,
        pause_between_phases:
          pendingSetup?.pause_between_phases || pausePreference,
      })
    },
    [pendingSetup, data, run],
  )

  const handleApprove = useCallback(() => {
    const url = pendingSetup?.url || data?.url
    if (!url) return
    // The approve run: deterministic build + render. No intent body —
    // intent.json is already confirmed; the storyboard_approved
    // marker flips server-side because phases include 5/6.
    void run.startRun({
      phases: [5, 6],
      url,
      source: pendingSetup?.source || data?.source || undefined,
    })
  }, [pendingSetup, data, run])

  // When the run pauses, auto-select the just-completed phase so the
  // user lands on the artifact they likely want to review. The hook's
  // pausedAfter is set when the paused event arrives and cleared on
  // resume / cancel, so this fires once per pause.
  useEffect(() => {
    if (run.status === 'paused' && run.pausedAfter !== null) {
      setSelected(run.pausedAfter)
    }
  }, [run.status, run.pausedAfter])

  // When a phase errors, open the inspector at that phase so the
  // user can reach the diagnostic report (especially important for
  // RENDER_BLOCKED in Phase 6, which contains the minimum-fix
  // recommendation). See #29.
  useEffect(() => {
    if (run.status !== 'error') return
    for (const [num, upd] of run.phaseUpdates) {
      if (upd.status === 'error') {
        setSelected(num)
        setInspectorOpen(true)
        break
      }
    }
  }, [run.status, run.phaseUpdates])

  // Auto-open the agent log when a run starts — but only when the
  // inspector is already open. The default window stays quiet; the
  // header sentence is its progress surface.
  useEffect(() => {
    const isRunning = run.status === 'starting' || run.status === 'running'
    if (isRunning && !wasRunningRef.current && inspectorOpen) {
      setLogOpen(true)
    }
    wasRunningRef.current = isRunning
  }, [run.status, inspectorOpen])

  // Esc closes the inspector. Skip when an input is focused (the
  // user is probably canceling an inline edit) and when a modal is
  // open (Dialog/AlertDialog own Esc for themselves).
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
      setInspectorOpen(false)
      setLogOpen(false)
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  // Project-wide cost (M1): the run ticker resets per run, and the
  // two-run cold start made that visible — the meter under-reported
  // by the exploration run's cost. state.json keeps per-phase costs
  // (the backend wipes a phase's entry when a new run includes it, so
  // summing state never double-counts the live ticker's phases);
  // while a run is active, add its live accumulation on top. On
  // terminal states the refetched state total is authoritative.
  const stateCost = Object.values(data?.phases ?? {}).reduce(
    (sum, p) => sum + (p?.cost_usd ?? 0),
    0,
  )
  const runActive =
    run.status === 'starting' ||
    run.status === 'running' ||
    run.status === 'paused'
  const displayCost = runActive
    ? stateCost + run.cumulativeCost
    : Math.max(stateCost, run.cumulativeCost)

  return (
    <div className="flex h-screen flex-col bg-background text-foreground">
      <Header
        projectName={projectName}
        url={url}
        loading={isLoading}
        runStatus={run.status}
        currentPhase={run.currentPhase}
        onCancel={() => void run.cancel()}
        onNewProject={() => setNewProjectOpen(true)}
        showNewProject={!empty}
        inspectorOpen={inspectorOpen}
        onToggleInspector={() => setInspectorOpen((v) => !v)}
        onOpenSettings={() => setVoiceOpen(true)}
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
                error={upd.error ?? run.error ?? 'Unknown error'}
                artifactShown={inspectorOpen && selected === num}
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
        // Intent confirmation card (M1 two-run flow): exploration
        // finished, proposal recorded, not yet confirmed. Derived
        // from /api/project so a reload mid-flow re-shows it.
        const phase1 = data?.phases?.['1']
        const runActive =
          run.status === 'starting' || run.status === 'running'
        if (
          runActive ||
          data?.intent_confirmed ||
          phase1?.status !== 'completed' ||
          !phase1?.intent_proposal
        ) {
          return null
        }
        return (
          <IntentConfirmCard
            proposal={phase1.intent_proposal}
            userIntent={pendingSetup?.intent ?? data?.intent ?? null}
            screens={phase1.screens}
            warnings={phase1.warnings}
            busy={false}
            onConfirm={handleIntentConfirm}
          />
        )
      })()}
      {(() => {
        // Empty project → the front door IS the stage (one-object
        // pass): hero URL + brief box, full width. Once a run starts
        // (or a project exists) the normal surfaces take over.
        const runActive =
          run.status === 'starting' || run.status === 'running'
        if (empty && !runActive) {
          return (
            <main className="flex min-h-0 flex-1">
              <StageEmpty
                projectDir={projectDir}
                submitting={run.status === 'starting'}
                onSubmit={handleNewProjectSubmit}
              />
            </main>
          )
        }

        // Storyboard as the center surface (M2): shown whenever a
        // storyboard exists (or the [2,3,4] leg is producing one)
        // and the demo hasn't rendered yet. After render,
        // video+segments take over (storyboard tab is M4).
        const videoDone = data?.phases?.['6']?.status === 'completed'
        const sbExists =
          storyboard.state.status === 'success' &&
          storyboard.state.data.exists
        const buildingStoryboard =
          (run.status === 'starting' || run.status === 'running') &&
          run.currentPhase !== null &&
          run.currentPhase >= 2 &&
          run.currentPhase <= 4
        const showStoryboard =
          !videoDone && (sbExists || buildingStoryboard)

        // The approve gate: rehearsed, unreviewed, not yet rendered.
        const phase4 = data?.phases?.['4']
        const gateOpen =
          !videoDone &&
          !data?.storyboard_approved &&
          sbExists &&
          (phase4?.status === 'completed' ||
            (phase4?.status === 'error' &&
              phase4?.explore_overall === 'BLOCKED'))

        return (
          <main className="flex min-h-0 flex-1">
            {showStoryboard ? (
              <div className="flex-[3] min-w-0 border-r border-border">
                <StoryboardView
                  state={storyboard.state}
                  refetch={storyboardRefetch}
                  runStatus={run.status}
                  currentPhase={run.currentPhase}
                  gateOpen={gateOpen}
                  liveShots={run.screenshots}
                  onApprove={handleApprove}
                  onRegenerate={() => setNewProjectOpen(true)}
                  approving={
                    (run.status === 'starting' ||
                      run.status === 'running') &&
                    run.currentPhase !== null &&
                    run.currentPhase >= 5
                  }
                />
              </div>
            ) : null}
            <div
              className={
                showStoryboard ? 'flex-[2] min-w-0' : 'flex-1 min-w-0'
              }
            >
              <RightPane
                runStatus={run.status}
                runCompleteToken={runCompleteToken}
                screenshots={run.screenshots}
                exploring={run.currentPhase === 1}
              />
            </div>
          </main>
        )
      })()}
      <Inspector
        open={inspectorOpen}
        onClose={() => setInspectorOpen(false)}
        phases={phases}
        selected={selected}
        onSelect={setSelected}
        runStatus={run.status}
        currentPhase={run.currentPhase}
        onRunPhase={empty ? undefined : handleRunPhase}
        log={run.log}
        logOpen={logOpen}
        onLogOpenChange={setLogOpen}
        totalCostUsd={displayCost}
        pauseBetweenPhases={pausePreference}
        onPauseChange={setPausePreference}
        loading={isLoading}
        triage={
          data?.phases?.['4']?.explore_overall === 'BLOCKED' &&
          data?.phases?.['4']?.explore_findings
            ? {
                findings: data.phases['4'].explore_findings,
                onRegenerate: () => setNewProjectOpen(true),
              }
            : null
        }
      />
      <VoiceDialog
        open={voiceOpen}
        onOpenChange={(open) => {
          setVoiceOpen(open)
          if (!open) voice.refetch()
        }}
        state={voice.state}
        apply={voice.apply}
        runActive={
          run.status === 'starting' ||
          run.status === 'running' ||
          run.status === 'paused'
        }
        videoExists={data?.phases?.['6']?.status === 'completed'}
        // The runCompleteToken signal: RightPane refetches segments
        // and busts the video cache — exactly what a re-voice needs.
        onReVoiced={() => setRunCompleteToken((t) => t + 1)}
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
          docs: '',
          // Prefill the full intent from /api/project (loaded from
          // intent.json or synthesized from describe). Lets a user
          // edit just one field (tone, focus) and regenerate.
          intent: data?.intent ?? {
            ...emptyIntent(),
            goal: data?.describe ?? '',
          },
        }}
        onSubmit={handleNewProjectSubmit}
        voiceSummary={
          voice.state.status === 'success'
            ? voice.state.data.ref_exists
              ? 'My cloned voice'
              : `${prettyVoiceName(voice.state.data.config.voice)} (stock)`
            : undefined
        }
        onOpenVoiceSettings={() => setVoiceOpen(true)}
      />
    </div>
  )
}

function prettyVoiceName(name: string): string {
  return name
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}
