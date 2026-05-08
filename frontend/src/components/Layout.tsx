import { useCallback, useState } from 'react'
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
import { useProject } from '@/hooks/useProject'
import { useRun } from '@/hooks/useRun'

const LOADING_PHASES: PhaseInfo[] = PHASE_NUMBERS.map((num) => ({
  num,
  name: ['Analyze', 'Narrate', 'Gather', 'Script', 'Validate'][num - 1] ?? '',
  status: 'pending',
}))

export function Layout() {
  const { state, refetch } = useProject()
  const run = useRun(refetch)
  const [selected, setSelected] = useState<number>(1)

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

  return (
    <div className="flex h-screen flex-col bg-background text-foreground">
      <Header
        projectName={projectName}
        url={url}
        loading={isLoading}
        runStatus={run.status}
        cumulativeCost={run.cumulativeCost}
        onCancel={() => void run.cancel()}
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
    </div>
  )
}
