import { useState } from 'react'
import {
  CircleCheck,
  CircleAlert,
  CircleX,
  Clapperboard,
  History,
  ImageOff,
  Loader2,
  Pencil,
  Play,
  RefreshCw,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { NarrationEditor } from './NarrationEditor'
import {
  patchSceneNarration,
  type SceneStatus,
  type StoryboardScene,
} from '@/api/storyboard'
import type { StoryboardFetchState } from '@/hooks/useStoryboard'
import type { RunStatus } from '@/hooks/useRun'

interface StoryboardViewProps {
  state: StoryboardFetchState
  refetch: () => void
  runStatus: RunStatus
  /** Phase currently executing (for the building placeholder). */
  currentPhase: number | null
  /** Gate state: show the approve bar when true. */
  gateOpen: boolean
  onApprove: () => void
  onRegenerate: () => void
  approving: boolean
  /** Live SSE screenshots — rehearsal shots (s<N>.png) bind to scene
   * cards optimistically while Phase 4 is still running. */
  liveShots?: { file: string; url: string }[]
}

/**
 * The storyboard — the product's primary review surface (M2).
 * Scenes as cards: rehearsal screenshot, narration (inline-editable
 * at the gate), status, and verification notices. Ends in the
 * approve bar: "Looks good — record it".
 */
export function StoryboardView({
  state,
  refetch,
  runStatus,
  currentPhase,
  gateOpen,
  onApprove,
  onRegenerate,
  approving,
  liveShots = [],
}: StoryboardViewProps) {
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editError, setEditError] = useState<string | null>(null)

  const runActive = runStatus === 'starting' || runStatus === 'running'

  if (state.status === 'loading') {
    return <CenteredNote icon="spinner" text="Loading storyboard…" />
  }
  if (state.status === 'error') {
    return <CenteredNote icon="none" text={`Storyboard error: ${state.error}`} />
  }
  const doc = state.data.storyboard
  if (!state.data.exists || !doc || doc.scenes.length === 0) {
    return (
      <CenteredNote
        icon={runActive ? 'spinner' : 'board'}
        text={
          runActive
            ? currentPhase === 2
              ? 'Planning your demo…'
              : 'Working…'
            : 'No storyboard yet — it appears once planning starts.'
        }
      />
    )
  }

  const scenes = doc.scenes
  const counts = {
    verified: scenes.filter((s) => s.status === 'verified').length,
    warn: scenes.filter((s) => s.status === 'warn').length,
    failed: scenes.filter((s) => s.status === 'failed').length,
  }
  const hasFailures = counts.failed > 0

  const handleSave = async (scene: StoryboardScene, narration: string) => {
    setEditError(null)
    try {
      await patchSceneNarration(scene.id, narration)
      setEditingId(null)
      refetch()
    } catch (err) {
      setEditError(err instanceof Error ? err.message : String(err))
    }
  }

  // In-flight rehearsal shots by scene index: "s3.png" → 3. Used as
  // optimistic thumbnails while Phase 4 runs (the canonical refs land
  // in the doc when the phase completes).
  const liveShotByIndex = new Map<number, string>()
  for (const shot of liveShots) {
    const match = /^s(\d+)\.png$/.exec(shot.file)
    if (match && shot.url.includes('/rehearsal/')) {
      liveShotByIndex.set(parseInt(match[1]!, 10), shot.url)
    }
  }

  const progressLabel = runActive
    ? currentPhase === 2
      ? 'Planning scenes…'
      : currentPhase === 3
        ? 'Finding selectors…'
        : currentPhase === 4
          ? 'Rehearsing against your app…'
          : currentPhase !== null && currentPhase >= 5
            ? 'Rendering your video…'
            : 'Working…'
    : null

  return (
    <div className="flex h-full flex-col">
      <div className="flex h-9 shrink-0 items-center gap-2 border-b border-border bg-muted/30 px-4">
        <Clapperboard className="size-4 text-muted-foreground" />
        <span className="text-sm font-medium">{doc.title}</span>
        {doc.summary ? (
          <span className="truncate text-xs text-muted-foreground">
            — {doc.summary}
          </span>
        ) : null}
        {progressLabel ? (
          <span className="ml-auto flex shrink-0 items-center gap-1.5 text-xs text-muted-foreground">
            <Loader2 className="size-3 animate-spin" />
            {progressLabel}
          </span>
        ) : null}
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3">
        <div className="mx-auto flex max-w-2xl flex-col gap-3">
          {scenes.map((scene) => (
            <SceneCard
              key={scene.id}
              scene={scene}
              liveShotUrl={liveShotByIndex.get(scene.index) ?? null}
              editing={editingId === scene.id}
              editError={editingId === scene.id ? editError : null}
              canEdit={gateOpen && !runActive && editingId === null}
              onBeginEdit={() => {
                setEditError(null)
                setEditingId(scene.id)
              }}
              onCancelEdit={() => {
                setEditError(null)
                setEditingId(null)
              }}
              onSave={(text) => handleSave(scene, text)}
            />
          ))}
          {runActive ? (
            <div className="flex h-24 animate-pulse items-center justify-center rounded-lg border border-dashed border-border text-sm text-muted-foreground">
              {currentPhase === 2
                ? 'Planning scenes…'
                : currentPhase === 3
                  ? 'Finding selectors…'
                  : currentPhase === 4
                    ? 'Rehearsing against your app…'
                    : 'Working…'}
            </div>
          ) : null}
        </div>
      </div>

      {gateOpen ? (
        <div className="shrink-0 border-t border-border bg-background/95 px-4 py-3">
          <div className="mx-auto flex max-w-2xl items-center justify-between gap-3">
            <div className="flex flex-col gap-0.5">
              <span className="text-sm">
                {scenes.length} scenes · {counts.verified} verified
                {counts.warn > 0 ? ` · ${counts.warn} warning${counts.warn > 1 ? 's' : ''}` : ''}
                {counts.failed > 0 ? (
                  <span className="text-destructive">
                    {' '}· {counts.failed} failed
                  </span>
                ) : null}
              </span>
              {hasFailures ? (
                <span className="text-xs text-muted-foreground">
                  Rehearsal hit problems — revise the brief and regenerate
                  before recording.
                </span>
              ) : null}
            </div>
            <div className="flex shrink-0 gap-2">
              {hasFailures ? (
                <Button variant="outline" onClick={onRegenerate}>
                  <RefreshCw className="size-4" />
                  Regenerate
                </Button>
              ) : null}
              <Button
                onClick={onApprove}
                disabled={hasFailures || runActive || approving}
              >
                {approving ? (
                  <>
                    <Loader2 className="size-4 animate-spin" />
                    Rendering…
                  </>
                ) : (
                  <>
                    <Play className="size-4" />
                    Looks good — record it
                  </>
                )}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}

function SceneCard({
  scene,
  liveShotUrl,
  editing,
  editError,
  canEdit,
  onBeginEdit,
  onCancelEdit,
  onSave,
}: {
  scene: StoryboardScene
  liveShotUrl: string | null
  editing: boolean
  editError: string | null
  canEdit: boolean
  onBeginEdit: () => void
  onCancelEdit: () => void
  onSave: (narration: string) => Promise<void>
}) {
  const verification = scene.verification
  const notice =
    scene.status === 'failed' || scene.status === 'warn'
      ? verification?.suggestion?.trim() || verification?.reason?.trim()
      : null
  const revisions = scene.revisions ?? []

  return (
    <Card className="gap-0 overflow-hidden p-0">
      <div className="flex items-center gap-2 border-b border-border bg-muted/20 px-4 py-2">
        <span className="font-mono text-xs text-muted-foreground">
          {String(scene.index).padStart(2, '0')}
        </span>
        <span className="min-w-0 flex-1 truncate text-sm font-medium">
          {scene.title}
        </span>
        <span className="rounded-full border border-border bg-background px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
          {scene.action}
        </span>
        <StatusChip status={scene.status} reason={verification?.reason} />
      </div>

      <div className="flex gap-3 px-4 py-3">
        {scene.rehearsal_screenshot || liveShotUrl ? (
          <img
            src={
              scene.rehearsal_screenshot
                ? `/api/project/rehearsal/${scene.rehearsal_screenshot}`
                : liveShotUrl!
            }
            alt={`Scene ${scene.index}: ${scene.title}`}
            className="h-24 shrink-0 rounded-md border border-border object-cover"
            loading="lazy"
          />
        ) : (
          <div className="flex h-24 w-36 shrink-0 items-center justify-center rounded-md border border-dashed border-border text-muted-foreground">
            <ImageOff className="size-5" />
          </div>
        )}
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <div className="flex items-start gap-1.5">
            <p className="min-w-0 flex-1 text-sm leading-relaxed">
              {scene.narration ? (
                scene.narration
              ) : (
                <span className="italic text-muted-foreground">(silent)</span>
              )}
            </p>
            {canEdit && !editing ? (
              <button
                type="button"
                onClick={onBeginEdit}
                className="rounded p-1 text-muted-foreground hover:bg-secondary hover:text-foreground"
                aria-label={`Edit narration for scene ${scene.index}`}
              >
                <Pencil className="size-3.5" />
              </button>
            ) : null}
          </div>
          {revisions.length > 0 ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="flex w-fit items-center gap-1 text-xs text-muted-foreground">
                  <History className="size-3" />
                  {revisions.length} revision{revisions.length > 1 ? 's' : ''}
                </span>
              </TooltipTrigger>
              <TooltipContent className="max-w-sm">
                <ul className="flex flex-col gap-1 text-xs">
                  {revisions.slice(-4).map((rev, i) => (
                    <li key={i}>
                      <span className="font-medium">{rev.type}</span>
                      {rev.reason ? ` — ${rev.reason}` : null}
                    </li>
                  ))}
                </ul>
              </TooltipContent>
            </Tooltip>
          ) : null}
        </div>
      </div>

      {notice ? (
        <div
          className={cn(
            'border-t px-4 py-2 text-xs',
            scene.status === 'failed'
              ? 'border-destructive/30 bg-destructive/10 text-destructive'
              : 'border-amber-500/30 bg-amber-500/10 text-status-warn',
          )}
        >
          {notice}
        </div>
      ) : null}

      {editing ? (
        <NarrationEditor
          initialNarration={scene.narration}
          error={editError}
          onSave={onSave}
          onCancel={onCancelEdit}
        />
      ) : null}
    </Card>
  )
}

function StatusChip({
  status,
  reason,
}: {
  status: SceneStatus
  reason?: string
}) {
  const config: Record<
    SceneStatus,
    { label: string; className: string; Icon: typeof CircleCheck }
  > = {
    verified: {
      label: 'verified',
      className: 'border-emerald-500/40 bg-emerald-500/10 text-status-ok',
      Icon: CircleCheck,
    },
    warn: {
      label: 'warning',
      className: 'border-amber-500/40 bg-amber-500/10 text-status-warn',
      Icon: CircleAlert,
    },
    failed: {
      label: 'failed',
      className: 'border-destructive/40 bg-destructive/10 text-destructive',
      Icon: CircleX,
    },
    planned: {
      label: 'draft',
      className: 'border-border bg-secondary/40 text-muted-foreground',
      Icon: Clapperboard,
    },
    hypothesized: {
      label: 'draft',
      className: 'border-border bg-secondary/40 text-muted-foreground',
      Icon: Clapperboard,
    },
  }
  const { label, className, Icon } = config[status] ?? config.planned
  const chip = (
    <span
      className={cn(
        'flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide',
        className,
      )}
    >
      <Icon className="size-3" />
      {label}
    </span>
  )
  if (!reason) return chip
  return (
    <Tooltip>
      <TooltipTrigger asChild>{chip}</TooltipTrigger>
      <TooltipContent className="max-w-sm text-xs">{reason}</TooltipContent>
    </Tooltip>
  )
}

function CenteredNote({
  icon,
  text,
}: {
  icon: 'spinner' | 'board' | 'none'
  text: string
}) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
      {icon === 'spinner' ? (
        <Loader2 className="size-5 animate-spin" />
      ) : icon === 'board' ? (
        <Clapperboard className="size-5" />
      ) : null}
      {text}
    </div>
  )
}
