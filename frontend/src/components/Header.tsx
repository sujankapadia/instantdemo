import { Loader2, RefreshCw, Settings, Square, Wrench } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import {
  REHEARSAL_PLANNING,
  rehearsalWalking,
  stageSentence,
} from '@/lib/labels'
import type { RunStatus } from '@/hooks/useRun'

interface HeaderProps {
  projectName: string
  url?: string | null
  loading?: boolean
  runStatus: RunStatus
  /** Currently-executing phase (1-6). Null when no phase is in
   *  flight. Rendered as a film-register sentence, never a number. */
  currentPhase: number | null
  /** Per-chapter progress within phases 2-4 (M7). */
  chapterProgress?: { current: number; total: number; name: string } | null
  /** Per-segment renderer progress within phase 6 (M8). */
  renderProgress?: {
    stage: 'narrating' | 'recording'
    current: number
    total: number
  } | null
  /** Rehearsal thumbnails seen this run (M8): drives the two-stage
   *  phase-4 sentence. */
  phase4ShotCount?: number
  onCancel: () => void
  onNewProject: () => void
  /** Hide the "Regenerate" button when the front door is the
   *  primary entry point (no project yet). */
  showNewProject?: boolean
  inspectorOpen: boolean
  onToggleInspector: () => void
  /** Opens the Voice & Pronunciation settings dialog (M3). */
  onOpenSettings: () => void
}

/**
 * Quiet chrome (one-object pass): wordmark, project, a progress
 * SENTENCE during runs, Stop/Regenerate, and two thresholds —
 * Inspector (wrench) and Voice (gear). No cost meter (it lives in
 * the Inspector), no mode toggle, no phase numbers.
 */
export function Header({
  projectName,
  url,
  loading,
  runStatus,
  currentPhase,
  chapterProgress,
  renderProgress,
  phase4ShotCount = 0,
  onCancel,
  onNewProject,
  showNewProject = true,
  inspectorOpen,
  onToggleInspector,
  onOpenSettings,
}: HeaderProps) {
  const isActive =
    runStatus === 'running' ||
    runStatus === 'starting' ||
    runStatus === 'paused'
  const showProgress = isActive && currentPhase !== null

  return (
    <header className="stage-chrome flex h-14 items-center justify-between border-b border-border bg-background px-4">
      <div className="flex items-baseline gap-3">
        <span className="text-base font-semibold">InstantDemo</span>
        {loading ? (
          <span className="text-sm text-muted-foreground">Loading…</span>
        ) : (
          <>
            <span className="text-sm text-muted-foreground">{projectName}</span>
            {url ? (
              <span className="text-xs text-muted-foreground/70">{url}</span>
            ) : null}
          </>
        )}
      </div>
      <div className="flex items-center gap-2">
        {showProgress ? (
          <span
            className="flex items-center gap-1.5 text-xs text-muted-foreground"
            aria-label="The studio is working"
          >
            <Loader2 className="size-3 animate-spin text-foreground/80" />
            <span>
              {currentPhase === 4
                ? phase4ShotCount === 0
                  ? REHEARSAL_PLANNING
                  : rehearsalWalking(phase4ShotCount)
                : stageSentence(currentPhase)}
              {chapterProgress
                ? ` — chapter ${chapterProgress.current} of ${chapterProgress.total}: “${chapterProgress.name}”`
                : ''}
              {renderProgress
                ? ` — ${renderProgress.stage} scene ${renderProgress.current} of ${renderProgress.total}`
                : ''}
            </span>
          </span>
        ) : null}
        {isActive ? (
          <Button
            size="sm"
            variant="destructive"
            onClick={onCancel}
            aria-label="Stop run"
          >
            <Square className="size-3" />
            Stop
          </Button>
        ) : showNewProject ? (
          <Button
            size="sm"
            variant="secondary"
            onClick={onNewProject}
            disabled={loading}
          >
            <RefreshCw className="size-3" />
            Regenerate
          </Button>
        ) : null}
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              aria-label={inspectorOpen ? 'Close inspector' : 'Open inspector'}
              onClick={onToggleInspector}
            >
              <Wrench />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">Inspector</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              aria-label="Voice & pronunciation settings"
              onClick={onOpenSettings}
            >
              <Settings />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            Voice &amp; pronunciation
          </TooltipContent>
        </Tooltip>
      </div>
    </header>
  )
}
