import { useCallback, useMemo, useRef, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { VideoPlayer } from './VideoPlayer'
import { SegmentsList, type EditingProps } from './SegmentsList'
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from './ui/resizable'
import { useSegments } from '@/hooks/useSegments'
import type { Segment } from '@/api/project'
import {
  deleteSegment,
  patchSegmentNarration,
  reRenderSegmentAudio,
} from '@/api/segments'
import type { RunStatus } from '@/hooks/useRun'

interface RightPaneProps {
  runStatus: RunStatus
}

export function RightPane({ runStatus }: RightPaneProps) {
  const segmentsState = useSegments()
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const [currentTimeS, setCurrentTimeS] = useState(0)
  const [videoVersion, setVideoVersion] = useState(() => Date.now())

  // Editing state — kept here so RightPane can coordinate with the
  // segments hook (refetch after re-render) and the video element
  // (cache-bust after re-render).
  const [editingIndex, setEditingIndex] = useState<number | null>(null)
  const [staleIndices, setStaleIndices] = useState<Set<number>>(
    () => new Set(),
  )
  const [rerenderingIndex, setRerenderingIndex] = useState<number | null>(
    null,
  )
  const [deletingIndex, setDeletingIndex] = useState<number | null>(null)
  const [errorByIndex, setErrorByIndex] = useState<Record<number, string>>(
    {},
  )

  const segments =
    segmentsState.state.status === 'success'
      ? segmentsState.state.data.segments
      : []
  const hasTiming =
    segmentsState.state.status === 'success' &&
    segmentsState.state.data.has_timing

  // Find which segment contains the current playback time.
  const currentIndex = useMemo<number | null>(() => {
    if (!hasTiming) return null
    for (const seg of segments) {
      if (seg.start_s === null || seg.end_s === null) continue
      if (currentTimeS >= seg.start_s && currentTimeS < seg.end_s) {
        return seg.index
      }
    }
    return null
  }, [segments, hasTiming, currentTimeS])

  const handleSeek = useCallback((seg: Segment) => {
    if (!videoRef.current || seg.start_s === null) return
    videoRef.current.currentTime = seg.start_s
    void videoRef.current.play()
  }, [])

  const handleBeginEdit = useCallback((index: number) => {
    setEditingIndex((prev) => (prev === null ? index : prev))
    // Clear any previous error for this segment when re-opening editor.
    setErrorByIndex((prev) => {
      if (!(index in prev)) return prev
      const next = { ...prev }
      delete next[index]
      return next
    })
  }, [])

  const handleCancelEdit = useCallback(() => {
    setEditingIndex(null)
  }, [])

  const handleSaveEdit = useCallback(
    async (index: number, narration: string) => {
      try {
        await patchSegmentNarration(index, narration)
        setStaleIndices((prev) => {
          const next = new Set(prev)
          next.add(index)
          return next
        })
        setErrorByIndex((prev) => {
          if (!(index in prev)) return prev
          const next = { ...prev }
          delete next[index]
          return next
        })
        setEditingIndex(null)
        // Refresh segments so the list reflects the new narration text.
        segmentsState.refetch()
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err)
        setErrorByIndex((prev) => ({ ...prev, [index]: msg }))
        // Leave the editor open so the user sees the error.
      }
    },
    [segmentsState],
  )

  const handleRerender = useCallback(
    async (index: number) => {
      if (rerenderingIndex !== null) return
      setRerenderingIndex(index)
      setErrorByIndex((prev) => {
        if (!(index in prev)) return prev
        const next = { ...prev }
        delete next[index]
        return next
      })
      try {
        await reRenderSegmentAudio(index)
        setStaleIndices((prev) => {
          if (!prev.has(index)) return prev
          const next = new Set(prev)
          next.delete(index)
          return next
        })
        // Bust the video element's cache so the new MP4 is fetched.
        setVideoVersion(Date.now())
        // Refresh segments — segment-timing.json was rewritten.
        segmentsState.refetch()
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err)
        setErrorByIndex((prev) => ({ ...prev, [index]: msg }))
      } finally {
        setRerenderingIndex(null)
      }
    },
    [rerenderingIndex, segmentsState],
  )

  const handleDelete = useCallback(
    async (index: number) => {
      if (deletingIndex !== null) return
      setDeletingIndex(index)
      setErrorByIndex((prev) => {
        if (!(index in prev)) return prev
        const next = { ...prev }
        delete next[index]
        return next
      })
      try {
        await deleteSegment(index)
        // The deleted segment's index disappears; any stale index >= the
        // deleted one shifts down by one. Rebuild stale set to reflect.
        setStaleIndices((prev) => {
          const next = new Set<number>()
          for (const i of prev) {
            if (i < index) next.add(i)
            else if (i > index) next.add(i - 1)
            // i === index drops out
          }
          return next
        })
        setEditingIndex(null)
        setVideoVersion(Date.now())
        segmentsState.refetch()
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err)
        setErrorByIndex((prev) => ({ ...prev, [index]: msg }))
      } finally {
        setDeletingIndex(null)
      }
    },
    [deletingIndex, segmentsState],
  )

  const segmentCount =
    segmentsState.state.status === 'success'
      ? segmentsState.state.data.segments.length
      : 0

  const editing: EditingProps = {
    editingIndex,
    staleIndices,
    rerenderingIndex,
    deletingIndex,
    errorByIndex,
    totalSegments: segmentCount,
    onBeginEdit: handleBeginEdit,
    onSaveEdit: handleSaveEdit,
    onCancelEdit: handleCancelEdit,
    onRerender: handleRerender,
    onDelete: handleDelete,
  }

  const listState = mapSegmentsListState(segmentsState.state)

  const opMessage =
    deletingIndex !== null
      ? `Deleting segment ${String(deletingIndex + 1).padStart(2, '0')} — re-encoding video and regenerating audio (~20–30s)…`
      : rerenderingIndex !== null
        ? `Re-rendering audio for segment ${String(rerenderingIndex + 1).padStart(2, '0')} (~20s)…`
        : null

  return (
    <aside className="flex h-full min-h-0 flex-col">
      {opMessage ? (
        <div className="flex shrink-0 items-center gap-2 border-b border-sky-500/30 bg-sky-500/10 px-4 py-2 text-xs text-sky-100">
          <Loader2 className="size-3.5 shrink-0 animate-spin text-sky-300" />
          <span>{opMessage}</span>
        </div>
      ) : null}
      <ResizablePanelGroup orientation="vertical">
        <ResizablePanel defaultSize={55} minSize={20}>
          <div className="h-full border-b border-border bg-muted/10 p-4">
            <VideoPlayer
              ref={videoRef}
              src={`/api/project/video?v=${videoVersion}`}
              onTimeUpdate={setCurrentTimeS}
            />
          </div>
        </ResizablePanel>
        <ResizableHandle withHandle />
        <ResizablePanel defaultSize={45} minSize={20}>
          <SegmentsList
            state={listState}
            currentIndex={currentIndex}
            onSelect={handleSeek}
            editing={editing}
            runStatus={runStatus}
          />
        </ResizablePanel>
      </ResizablePanelGroup>
    </aside>
  )
}

function mapSegmentsListState(
  state: ReturnType<typeof useSegments>['state'],
): React.ComponentProps<typeof SegmentsList>['state'] {
  if (state.status === 'loading') return { status: 'loading' }
  if (state.status === 'error') return { status: 'error', error: state.error }
  if (!state.data.exists) return { status: 'empty' }
  return {
    status: 'success',
    segments: state.data.segments,
    hasTiming: state.data.has_timing,
  }
}
