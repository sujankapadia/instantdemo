import { useEffect, useRef } from 'react'
import { Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { Segment } from '@/api/project'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'

interface SegmentsListProps {
  state:
    | { status: 'loading' }
    | { status: 'success'; segments: Segment[]; hasTiming: boolean }
    | { status: 'error'; error: string }
    | { status: 'empty' }
  currentIndex: number | null
  onSelect: (segment: Segment) => void
}

export function SegmentsList({
  state,
  currentIndex,
  onSelect,
}: SegmentsListProps) {
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
}: {
  segments: Segment[]
  hasTiming: boolean
  currentIndex: number | null
  onSelect: (segment: Segment) => void
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
}: {
  segment: Segment
  hasTiming: boolean
  active: boolean
  onSelect: (segment: Segment) => void
}) {
  const seekable = hasTiming && segment.start_s !== null
  const indexLabel = String(segment.index + 1).padStart(2, '0')
  const narration = segment.narration?.trim() || '(no narration)'

  const row = (
    <button
      type="button"
      data-segment-index={segment.index}
      onClick={() => seekable && onSelect(segment)}
      disabled={!seekable}
      className={cn(
        'grid w-full grid-cols-[2.25rem_minmax(3.5rem,auto)_minmax(4rem,auto)_1fr] items-center gap-3 px-4 py-2 text-left text-sm transition-colors',
        seekable
          ? 'cursor-pointer hover:bg-secondary/50'
          : 'cursor-default text-muted-foreground',
        active && 'bg-secondary/80 text-foreground',
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
      <span className="truncate text-foreground/90">{narration}</span>
    </button>
  )

  // Tooltip with full narration when truncated.
  return (
    <Tooltip>
      <TooltipTrigger asChild>{row}</TooltipTrigger>
      <TooltipContent side="left" className="max-w-sm">
        <p className="text-xs leading-relaxed">{narration}</p>
      </TooltipContent>
    </Tooltip>
  )
}

function formatTimestamp(s: number): string {
  const totalSeconds = Math.floor(s)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}
