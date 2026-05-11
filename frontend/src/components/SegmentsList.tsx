import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, Loader2, Pencil, RotateCcw, Trash2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import type { Segment } from '@/api/project'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import type { RunStatus } from '@/hooks/useRun'

export interface SegmentsListState {
  state:
    | { status: 'loading' }
    | { status: 'success'; segments: Segment[]; hasTiming: boolean }
    | { status: 'error'; error: string }
    | { status: 'empty' }
}

interface SegmentsListProps {
  state: SegmentsListState['state']
  currentIndex: number | null
  onSelect: (segment: Segment) => void
  /** Editing controls — undefined disables editing affordances entirely. */
  editing?: EditingProps
  runStatus: RunStatus
}

export interface EditingProps {
  /** Index of the segment currently being edited inline, or null. */
  editingIndex: number | null
  /** Set of indices that have been edited but not re-rendered yet. */
  staleIndices: Set<number>
  /** Index whose audio is currently being re-rendered. */
  rerenderingIndex: number | null
  /** Index currently being deleted (cut + re-mux in progress). */
  deletingIndex: number | null
  /** Per-segment error messages (PATCH / re-render / delete failures). */
  errorByIndex: Record<number, string>
  /** Total segment count — used to disable delete when only one is left. */
  totalSegments: number
  onBeginEdit: (index: number) => void
  onSaveEdit: (index: number, narration: string) => Promise<void>
  onCancelEdit: () => void
  onRerender: (index: number) => Promise<void>
  onDelete: (index: number) => Promise<void>
}

export function SegmentsList({
  state,
  currentIndex,
  onSelect,
  editing,
  runStatus,
}: SegmentsListProps) {
  const isRunActive =
    runStatus === 'running' ||
    runStatus === 'starting' ||
    runStatus === 'paused'

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex h-9 shrink-0 items-center justify-between border-b border-border bg-muted/30 px-4">
        <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Segments
        </span>
        {state.status === 'success' ? (
          <span className="text-xs text-muted-foreground/80">
            {state.segments.length} total
          </span>
        ) : null}
      </div>

      <div className="flex-1 min-h-0 overflow-auto">
        {state.status === 'loading' && <ListLoading />}
        {state.status === 'error' && <ListError message={state.error} />}
        {state.status === 'empty' && <ListEmpty />}
        {state.status === 'success' && (
          <SegmentsBody
            segments={state.segments}
            hasTiming={state.hasTiming}
            currentIndex={currentIndex}
            onSelect={onSelect}
            editing={editing}
            isRunActive={isRunActive}
          />
        )}
      </div>
    </div>
  )
}

function ListLoading() {
  return (
    <div className="flex h-full items-center justify-center text-muted-foreground">
      <Loader2 className="size-4 animate-spin" />
      <span className="ml-2 text-sm">Loading…</span>
    </div>
  )
}

function ListError({ message }: { message: string }) {
  return (
    <div className="flex h-full items-center justify-center p-4 text-center">
      <p className="text-sm text-destructive">Failed to load: {message}</p>
    </div>
  )
}

function ListEmpty() {
  return (
    <div className="flex h-full items-center justify-center p-4 text-center">
      <p className="max-w-xs text-sm text-muted-foreground">
        No script generated yet. Run Phase 4 to produce
        {' '}
        <code className="rounded bg-muted px-1 py-0.5 text-xs">demo-script.json</code>
        .
      </p>
    </div>
  )
}

function SegmentsBody({
  segments,
  hasTiming,
  currentIndex,
  onSelect,
  editing,
  isRunActive,
}: {
  segments: Segment[]
  hasTiming: boolean
  currentIndex: number | null
  onSelect: (segment: Segment) => void
  editing?: EditingProps
  isRunActive: boolean
}) {
  const containerRef = useRef<HTMLDivElement>(null)

  // Auto-scroll the active row into view when the playing segment changes.
  useEffect(() => {
    if (currentIndex === null || !containerRef.current) return
    const row = containerRef.current.querySelector<HTMLElement>(
      `[data-segment-index="${currentIndex}"]`,
    )
    if (row) {
      row.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    }
  }, [currentIndex])

  if (segments.length === 0) {
    return (
      <div className="flex h-full items-center justify-center p-4 text-center">
        <p className="text-sm text-muted-foreground">
          The script has no segments.
        </p>
      </div>
    )
  }

  return (
    <div ref={containerRef} className="divide-y divide-border/60">
      {!hasTiming ? <StaleTimingBanner /> : null}
      {segments.map((seg) => (
        <SegmentRow
          key={seg.index}
          segment={seg}
          hasTiming={hasTiming}
          active={currentIndex === seg.index}
          onSelect={onSelect}
          editing={editing}
          isRunActive={isRunActive}
        />
      ))}
    </div>
  )
}

function StaleTimingBanner() {
  return (
    <div className="border-b border-amber-500/30 bg-amber-500/10 px-4 py-2 text-xs text-amber-300">
      Playback timing is stale or missing. Re-render the demo to enable
      click-to-seek.
    </div>
  )
}

function SegmentRow({
  segment,
  hasTiming,
  active,
  onSelect,
  editing,
  isRunActive,
}: {
  segment: Segment
  hasTiming: boolean
  active: boolean
  onSelect: (segment: Segment) => void
  editing?: EditingProps
  isRunActive: boolean
}) {
  const seekable = hasTiming && segment.start_s !== null
  const indexLabel = String(segment.index + 1).padStart(2, '0')
  const narration = segment.narration?.trim() || '(no narration)'
  const isBeingEdited = editing?.editingIndex === segment.index
  const isStale = editing?.staleIndices.has(segment.index) ?? false
  const isRerendering = editing?.rerenderingIndex === segment.index
  const isDeleting = editing?.deletingIndex === segment.index
  const anyDeleting =
    editing?.deletingIndex !== null && editing?.deletingIndex !== undefined
  const error = editing?.errorByIndex[segment.index]
  const editingDisabled =
    isRunActive ||
    isRerendering ||
    anyDeleting ||
    (editing?.editingIndex !== null &&
      editing?.editingIndex !== undefined &&
      editing.editingIndex !== segment.index)
  const editingDisabledReason = isRunActive
    ? 'Wait for the current run to finish'
    : isRerendering
      ? 'Re-rendering audio…'
      : anyDeleting
        ? 'Deleting a segment…'
        : editing?.editingIndex !== null && editing?.editingIndex !== undefined
          ? 'Finish editing the current segment first'
          : ''
  const onlySegment = (editing?.totalSegments ?? 0) <= 1
  const deleteDisabled = editingDisabled || isBeingEdited || onlySegment
  const deleteDisabledReason = onlySegment
    ? "Can't delete the only segment"
    : editingDisabledReason

  // Use a div + role=button rather than a real <button>: when the row
  // is non-seekable (no timing data) we want click-to-seek disabled,
  // but a disabled <button> blocks click events on its children too,
  // which would prevent the nested pencil / re-render icons from
  // working. A div lets us conditionally handle the seek without
  // disabling child clicks.
  const handleRowClick = () => {
    if (seekable && !isBeingEdited) onSelect(segment)
  }
  const handleRowKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if ((e.key === 'Enter' || e.key === ' ') && seekable && !isBeingEdited) {
      e.preventDefault()
      onSelect(segment)
    }
  }

  const row = (
    <div
      role="button"
      tabIndex={seekable && !isBeingEdited ? 0 : -1}
      data-segment-index={segment.index}
      onClick={handleRowClick}
      onKeyDown={handleRowKeyDown}
      aria-disabled={!seekable || isBeingEdited}
      className={cn(
        'group grid w-full grid-cols-[2.25rem_minmax(3.5rem,auto)_minmax(4rem,auto)_1fr_auto] items-center gap-3 px-4 py-2 text-left text-sm transition-colors',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        seekable && !isBeingEdited
          ? 'cursor-pointer hover:bg-secondary/50'
          : 'cursor-default text-muted-foreground',
        active && 'bg-secondary/80 text-foreground',
        isBeingEdited && 'bg-secondary/40',
      )}
    >
      <span
        className={cn(
          'font-mono text-xs',
          active ? 'text-foreground' : 'text-muted-foreground',
        )}
      >
        {indexLabel}
      </span>
      <span
        className={cn(
          'font-mono text-xs tabular-nums',
          active ? 'text-foreground' : 'text-muted-foreground/80',
        )}
      >
        {hasTiming && segment.start_s !== null
          ? formatTimestamp(segment.start_s)
          : '—'}
      </span>
      <span
        className={cn(
          'inline-flex shrink-0 items-center justify-center rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide',
          active ? 'bg-foreground/15 text-foreground' : 'bg-secondary/60 text-muted-foreground',
        )}
      >
        {segment.action}
      </span>
      <span className="flex min-w-0 items-center gap-1.5 text-foreground/90">
        {segment.audio_overflows ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <AlertTriangle
                className="size-3.5 shrink-0 text-amber-400"
                aria-label="Audio overflow"
              />
            </TooltipTrigger>
            <TooltipContent side="left" className="max-w-xs">
              <p className="text-xs leading-relaxed">
                The narration audio is longer than the video frames
                recorded for this segment. Playback will be cut off
                mid-sentence. Re-record the demo (Phase 5) to fix.
              </p>
            </TooltipContent>
          </Tooltip>
        ) : null}
        <span className="truncate">{narration}</span>
      </span>
      {editing ? (
        <div className="flex items-center gap-1">
          {isStale ? (
            <RowIconButton
              icon={
                isRerendering ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  <RotateCcw className="size-3.5" />
                )
              }
              label="Re-render audio"
              onClick={() => void editing.onRerender(segment.index)}
              disabled={editingDisabled}
              disabledReason={editingDisabledReason}
              accentClass={isStale ? 'text-amber-400' : undefined}
              alwaysVisible
            />
          ) : null}
          <RowIconButton
            icon={<Pencil className="size-3.5" />}
            label="Edit narration"
            onClick={() => editing.onBeginEdit(segment.index)}
            disabled={editingDisabled || isBeingEdited}
            disabledReason={editingDisabledReason}
          />
          <DeleteSegmentButton
            segmentIndex={segment.index}
            isDeleting={isDeleting}
            disabled={deleteDisabled}
            disabledReason={deleteDisabledReason}
            narrationPreview={narration}
            onConfirm={() => void editing.onDelete(segment.index)}
          />
        </div>
      ) : null}
    </div>
  )

  return (
    <div>
      {seekable ? (
        <Tooltip>
          <TooltipTrigger asChild>{row}</TooltipTrigger>
          <TooltipContent side="left" className="max-w-sm">
            <p className="text-xs leading-relaxed">{narration}</p>
          </TooltipContent>
        </Tooltip>
      ) : (
        row
      )}
      {isBeingEdited && editing ? (
        <SegmentEditor
          initialNarration={segment.narration}
          rerendering={isRerendering}
          error={error ?? null}
          onSave={(text) => editing.onSaveEdit(segment.index, text)}
          onCancel={editing.onCancelEdit}
        />
      ) : null}
      {!isBeingEdited && error ? (
        <p className="px-4 pb-2 text-xs text-destructive">{error}</p>
      ) : null}
    </div>
  )
}

function DeleteSegmentButton({
  segmentIndex,
  isDeleting,
  disabled,
  disabledReason,
  narrationPreview,
  onConfirm,
}: {
  segmentIndex: number
  isDeleting: boolean
  disabled: boolean
  disabledReason?: string
  narrationPreview: string
  onConfirm: () => void
}) {
  const [open, setOpen] = useState(false)
  const segmentLabel = String(segmentIndex + 1).padStart(2, '0')

  return (
    <>
      <RowIconButton
        icon={
          isDeleting ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <Trash2 className="size-3.5" />
          )
        }
        label="Delete segment"
        onClick={() => setOpen(true)}
        disabled={disabled || isDeleting}
        disabledReason={disabledReason}
        accentClass="text-muted-foreground/60 hover:text-destructive"
      />
      <AlertDialog open={open} onOpenChange={setOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete segment {segmentLabel}?</AlertDialogTitle>
            <AlertDialogDescription className="space-y-2">
              <span className="block italic">"{narrationPreview}"</span>
              <span className="block">
                The frames for this segment will be cut out of the video
                and audio regenerated for the remaining segments. This
                takes around 30 seconds and can't be undone without
                re-recording the demo (Phase 5).
              </span>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={onConfirm}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Delete segment
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}


function RowIconButton({
  icon,
  label,
  onClick,
  disabled,
  disabledReason,
  accentClass,
  alwaysVisible,
}: {
  icon: React.ReactNode
  label: string
  onClick: () => void
  disabled?: boolean
  disabledReason?: string
  accentClass?: string
  alwaysVisible?: boolean
}) {
  const button = (
    <span
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-label={label}
      aria-disabled={disabled}
      onClick={(e) => {
        e.stopPropagation()
        if (!disabled) onClick()
      }}
      onKeyDown={(e) => {
        if ((e.key === 'Enter' || e.key === ' ') && !disabled) {
          e.preventDefault()
          e.stopPropagation()
          onClick()
        }
      }}
      className={cn(
        'inline-flex size-5 items-center justify-center rounded transition-opacity',
        disabled
          ? 'cursor-not-allowed opacity-30 hover:bg-transparent'
          : 'cursor-pointer hover:bg-secondary hover:text-foreground',
        accentClass ?? 'text-muted-foreground/60',
        alwaysVisible
          ? 'opacity-100'
          : 'opacity-0 group-hover:opacity-100 focus-within:opacity-100',
      )}
    >
      {icon}
    </span>
  )

  // Always show a tooltip — the icons are too small to communicate
  // their purpose by glyph alone. When disabled, the disabled reason
  // takes precedence over the action label.
  const tooltipText = disabled && disabledReason ? disabledReason : label
  return (
    <Tooltip>
      <TooltipTrigger asChild>{button}</TooltipTrigger>
      <TooltipContent side="left">{tooltipText}</TooltipContent>
    </Tooltip>
  )
}

function SegmentEditor({
  initialNarration,
  rerendering,
  error,
  onSave,
  onCancel,
}: {
  initialNarration: string
  rerendering: boolean
  error: string | null
  onSave: (narration: string) => Promise<void>
  onCancel: () => void
}) {
  const [text, setText] = useState(initialNarration)
  const [saving, setSaving] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    textareaRef.current?.focus()
  }, [])

  const handleSave = async () => {
    if (saving || rerendering || !text.trim()) return
    setSaving(true)
    try {
      await onSave(text.trim())
    } finally {
      setSaving(false)
    }
  }

  const busy = saving || rerendering
  const dirty = text.trim() !== initialNarration.trim()

  return (
    <div className="border-t border-border bg-background px-4 py-3">
      <textarea
        ref={textareaRef}
        value={text}
        onChange={(e) => setText(e.target.value)}
        disabled={busy}
        rows={4}
        className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50 resize-y"
        placeholder="Narration…"
      />
      {error ? (
        <p className="mt-2 text-xs text-destructive">{error}</p>
      ) : null}
      <div className="mt-2 flex justify-end gap-2">
        <Button
          size="sm"
          variant="ghost"
          onClick={onCancel}
          disabled={busy}
        >
          Cancel
        </Button>
        <Button
          size="sm"
          onClick={() => void handleSave()}
          disabled={busy || !dirty || !text.trim()}
        >
          {saving ? (
            <>
              <Loader2 className="size-3 animate-spin" />
              Saving…
            </>
          ) : (
            'Save'
          )}
        </Button>
      </div>
    </div>
  )
}

function formatTimestamp(s: number): string {
  const totalSeconds = Math.floor(s)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}
