import { useCallback, useMemo, useRef, useState } from 'react'
import { VideoPlayer } from './VideoPlayer'
import { SegmentsList } from './SegmentsList'
import { useSegments } from '@/hooks/useSegments'
import type { Segment } from '@/api/project'

export function RightPane() {
  const segmentsState = useSegments()
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const [currentTimeS, setCurrentTimeS] = useState(0)

  const segments =
    segmentsState.status === 'success' ? segmentsState.data.segments : []
  const hasTiming =
    segmentsState.status === 'success' && segmentsState.data.has_timing

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

  const listState = mapSegmentsListState(segmentsState)

  return (
    <aside className="flex h-full min-h-0 flex-col">
      <div className="border-b border-border bg-muted/10 p-4">
        <VideoPlayer
          ref={videoRef}
          src="/api/project/video"
          onTimeUpdate={setCurrentTimeS}
        />
      </div>
      <div className="flex-1 min-h-0">
        <SegmentsList
          state={listState}
          currentIndex={currentIndex}
          onSelect={handleSeek}
        />
      </div>
    </aside>
  )
}

function mapSegmentsListState(
  state: ReturnType<typeof useSegments>,
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
