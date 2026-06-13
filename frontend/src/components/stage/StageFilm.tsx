import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Download, History, Loader2, Undo2, Wand2 } from 'lucide-react'
import { Button } from '../ui/button'
import { VideoPlayer } from '../VideoPlayer'
import { SegmentsList, type EditingProps } from '../SegmentsList'
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from '../ui/resizable'
import { useSegments } from '@/hooks/useSegments'
import type { Segment } from '@/api/project'
import {
  deleteSegment,
  patchSegmentNarration,
  reRenderSegmentAudio,
} from '@/api/segments'
import {
  describeTake,
  fetchTakes,
  restoreTake,
  takeVideoUrl,
  type Take,
} from '@/api/takes'
import { reviseDemo, type ReviseResponse } from '@/api/revise'
import type { RunStatus } from '@/hooks/useRun'

interface StageFilmProps {
  runStatus: RunStatus
  /** Incremented by Layout each time a run finishes (via useRun.onComplete).
   *  The film stage reacts to the token bump by refetching scenes and
   *  busting the video cache — one-way signal, no transition heuristics. */
  runCompleteToken: number
  /** Lights-down signal: true while the film plays. */
  onPlayingChange?: (playing: boolean) => void
  /** Voice-suggestion answers open the Voice dialog. */
  onOpenVoice?: () => void
  /** Faster-pacing answers offer a re-record ([6] run). */
  onRerecord?: () => void
  /** The storyboard's scenes (upstream truth) — chapter grouping
   * over the scenes pane when counts align (M5b). */
  storyboardScenes?: { section?: unknown; [key: string]: unknown }[]
  /** Starts the scoped revision run ([2,3,4] + scope). */
  onReviseChapter?: (section: string, instruction: string) => void
}

export function StageFilm({
  runStatus,
  runCompleteToken,
  onPlayingChange,
  onOpenVoice,
  onRerecord,
  storyboardScenes,
  onReviseChapter,
}: StageFilmProps) {
  const segmentsState = useSegments()
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const [currentTimeS, setCurrentTimeS] = useState(0)
  const [videoVersion, setVideoVersion] = useState(() => Date.now())

  // Refetch segments + bust the video cache when a run completes.
  // useSegments already fetches on mount; this handles every subsequent
  // run. Skipped on initial render (token starts at 0) to avoid the
  // duplicate fetch. refetch is useCallback'd inside useSegments so
  // its identity is stable; including it in deps is safe.
  const segmentsRefetch = segmentsState.refetch
  useEffect(() => {
    if (runCompleteToken === 0) return
    segmentsRefetch()
    setVideoVersion(Date.now())
  }, [runCompleteToken, segmentsRefetch])

  // Versioned takes (M4): "your previous version is kept." Viewing a
  // prior take swaps the player's src — comparison by watching;
  // restore underneath (DESIGN.md principle 7).
  const [allTakes, setAllTakes] = useState<Take[]>([])
  const [viewingTake, setViewingTake] = useState<number | null>(null)
  const [restoring, setRestoring] = useState(false)
  const [takeError, setTakeError] = useState<string | null>(null)
  // Refetch the take list on mount, on the run-complete token, AND
  // whenever a run settles (runStatus leaves running/starting). The
  // token alone proved unreliable after a gate-approve render — the
  // picker could sit empty until a manual reload (#96). Settling is
  // the robust signal. On error, KEEP the last good list — a
  // transient refresh failure must never erase a working picker.
  useEffect(() => {
    if (runStatus === 'starting' || runStatus === 'running') return
    let cancelled = false
    fetchTakes()
      .then((takes) => {
        if (!cancelled) setAllTakes(takes)
      })
      .catch(() => {
        /* keep the last good list (#96) */
      })
    return () => {
      cancelled = true
    }
  }, [runCompleteToken, runStatus])
  // A take is only a "previous version" if it differs from the
  // current film — a fresh post-render snapshot is excluded so the
  // toggle never offers a no-op comparison.
  const playableTakes = allTakes.filter(
    (t) => t.video_exists && !t.is_current,
  )

  const handleRestore = async (n: number) => {
    setRestoring(true)
    setTakeError(null)
    try {
      await restoreTake(n)
      setViewingTake(null)
      setVideoVersion(Date.now())
      segmentsRefetch()
      fetchTakes().then(setAllTakes).catch(() => {})
    } catch (err) {
      setTakeError(err instanceof Error ? err.message : String(err))
    } finally {
      setRestoring(false)
    }
  }

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

  // Chapter spans over the scenes pane (M5b): derived from the
  // storyboard, index-aligned — only when scene/segment counts match
  // (a post-cut project diverges → flat list, full regenerate is
  // its path).
  const chapterSpans = useMemo(() => {
    const scenes = storyboardScenes ?? []
    if (scenes.length === 0 || scenes.length !== segmentCount) return []
    const spans: { name: string; startIndex: number; count: number }[] = []
    scenes.forEach((scene, i) => {
      const name =
        typeof scene.section === 'string' && scene.section.trim()
          ? scene.section
          : null
      if (!name) return
      const last = spans[spans.length - 1]
      if (last && last.name === name) last.count += 1
      else spans.push({ name, startIndex: i, count: 1 })
    })
    return spans
  }, [storyboardScenes, segmentCount])

  // The Revise dialog (M5b): chapter name + instruction box.
  const [revisingChapter, setRevisingChapter] = useState<string | null>(null)
  const [reviseText, setReviseText] = useState('')

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

  // The style/pace pass (M4): one instruction about the whole film.
  const [styleText, setStyleText] = useState('')
  const [styleBusy, setStyleBusy] = useState(false)
  const [styleResult, setStyleResult] = useState<ReviseResponse | null>(null)
  const [styleError, setStyleError] = useState<string | null>(null)

  const handleStyleSubmit = async () => {
    const instruction = styleText.trim()
    if (!instruction || styleBusy) return
    setStyleBusy(true)
    setStyleError(null)
    setStyleResult(null)
    try {
      const result = await reviseDemo(instruction)
      setStyleResult(result)
      if (
        result.kind === 'rewrite' ||
        (result.kind === 'pace' && !result.needs_rerecord)
      ) {
        setStyleText('')
        setViewingTake(null)
        setVideoVersion(Date.now())
        segmentsRefetch()
        fetchTakes().then(setAllTakes).catch(() => {})
        // The change is felt, not reported: seek to the first
        // changed scene and play it once timing refetches.
        const target = result.first_changed_index
        if (target !== null) {
          setTimeout(() => {
            const seg =
              segmentsState.state.status === 'success'
                ? segmentsState.state.data.segments.find(
                    (s) => s.index === target,
                  )
                : undefined
            const video = videoRef.current
            if (video && seg?.start_s != null) {
              video.currentTime = seg.start_s
              void video.play()
            }
          }, 800)
        }
      }
    } catch (err) {
      setStyleError(err instanceof Error ? err.message : String(err))
    } finally {
      setStyleBusy(false)
    }
  }

  const opMessage = styleBusy
    ? 'Revising the whole film — rewording and re-recording the narration (about a minute)…'
    : deletingIndex !== null
      ? `Cutting scene ${String(deletingIndex + 1).padStart(2, '0')} and rebuilding the film (~30 seconds)…`
      : rerenderingIndex !== null
        ? `Re-recording the narration for scene ${String(rerenderingIndex + 1).padStart(2, '0')} (~20 seconds)…`
        : null

  return (
    <aside className="flex h-full min-h-0 flex-col">
      {opMessage ? (
        <>
          <div className="flex shrink-0 items-center gap-2 border-b border-sky-500/30 bg-sky-500/10 px-4 py-2 text-xs text-sky-100">
            <Loader2 className="size-3.5 shrink-0 animate-spin text-sky-300" />
            <span>{opMessage}</span>
          </div>
          {/* Full-viewport click-blocker. Transparent — relies on the
              banner above (z-50) for the visible signal. Catches all
              pointer events under z-40 so the user can't trigger
              concurrent ops or navigate away while a delete or
              re-render is in flight. */}
          <div
            className="fixed inset-0 z-40 cursor-wait"
            aria-hidden="true"
          />
        </>
      ) : null}
      <ResizablePanelGroup orientation="vertical">
        <ResizablePanel defaultSize={55} minSize={20}>
          <div className="flex h-full flex-col border-b border-border bg-muted/10 p-4">
            <div className="stage-chrome mb-2 flex shrink-0 items-center gap-2 text-xs">
              <input
                value={styleText}
                onChange={(e) => setStyleText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') void handleStyleSubmit()
                }}
                placeholder={'Adjust the whole demo — "less jargon", "slower", "warmer"…'}
                disabled={styleBusy}
                aria-label="Adjust the whole demo"
                className="min-w-0 flex-1 rounded-md border border-input bg-background px-2.5 py-1.5 text-xs placeholder:text-muted-foreground/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
              />
              <Button
                size="xs"
                variant="outline"
                disabled={styleBusy || !styleText.trim()}
                onClick={() => void handleStyleSubmit()}
              >
                {styleBusy ? (
                  <Loader2 className="size-3 animate-spin" />
                ) : (
                  <Wand2 className="size-3" />
                )}
                Adjust
              </Button>
              {/* The deliverable (M6): one click — film + captions. */}
              <a
                href="/api/project/download"
                className="inline-flex items-center gap-1 rounded px-1.5 py-1 text-xs text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <Download className="size-3" />
                Download
              </a>
              {takeError ? (
                <span className="text-destructive">{takeError}</span>
              ) : null}
              {playableTakes.length > 0 && viewingTake !== null ? (
                <>
                  <span className="text-muted-foreground">
                    {(() => {
                      const t = allTakes.find((x) => x.n === viewingTake)
                      return t ? `Viewing ${describeTake(t)}` : `Viewing take ${viewingTake}`
                    })()}{' '}
                    — your current cut is kept
                  </span>
                  <Button
                    size="xs"
                    variant="outline"
                    disabled={restoring}
                    onClick={() => void handleRestore(viewingTake)}
                  >
                    {restoring ? (
                      <Loader2 className="size-3 animate-spin" />
                    ) : (
                      <Undo2 className="size-3" />
                    )}
                    Make this the current cut
                  </Button>
                  <Button
                    size="xs"
                    variant="ghost"
                    onClick={() => setViewingTake(null)}
                  >
                    Back to current
                  </Button>
                </>
              ) : playableTakes.length > 0 ? (
                <>
                  {playableTakes.length > 1 ? (
                    <select
                      aria-label="Choose a previous version"
                      className="rounded-md border border-input bg-background px-1.5 py-1 text-xs text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      value=""
                      onChange={(e) => {
                        const n = parseInt(e.target.value, 10)
                        if (!Number.isNaN(n)) setViewingTake(n)
                      }}
                    >
                      <option value="" disabled>
                        earlier takes…
                      </option>
                      {playableTakes.slice(1).map((t) => (
                        <option key={t.n} value={t.n}>
                          {describeTake(t)}
                        </option>
                      ))}
                    </select>
                  ) : null}
                  <Button
                    size="xs"
                    variant="ghost"
                    onClick={() => setViewingTake(playableTakes[0]!.n)}
                  >
                    <History className="size-3" />
                    Previous take
                  </Button>
                </>
              ) : null}
            </div>
            {styleError ? (
              <p className="mb-2 shrink-0 text-xs text-destructive">
                {styleError}
              </p>
            ) : null}
            {styleResult ? (
              <div className="studio-voice mb-2 flex shrink-0 flex-wrap items-center gap-2 rounded-md border border-border bg-secondary/20 px-3 py-2 text-sm">
                <span className="min-w-0 flex-1">
                  {styleResult.explanation}
                </span>
                {styleResult.kind === 'voice' && onOpenVoice ? (
                  <Button size="xs" variant="outline" onClick={onOpenVoice}>
                    Open Voice settings
                  </Button>
                ) : null}
                {styleResult.needs_rerecord && onRerecord ? (
                  <Button
                    size="xs"
                    variant="outline"
                    onClick={() => {
                      setStyleResult(null)
                      onRerecord()
                    }}
                  >
                    Re-record to apply (~2 min)
                  </Button>
                ) : null}
                <button
                  type="button"
                  aria-label="Dismiss"
                  className="text-muted-foreground hover:text-foreground"
                  onClick={() => setStyleResult(null)}
                >
                  ×
                </button>
              </div>
            ) : null}
            <div className="min-h-0 flex-1">
              <VideoPlayer
                ref={videoRef}
                src={
                  viewingTake !== null
                    ? takeVideoUrl(viewingTake)
                    : `/api/project/video?v=${videoVersion}`
                }
                onTimeUpdate={setCurrentTimeS}
                onPlayingChange={onPlayingChange}
              />
            </div>
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
            chapters={chapterSpans}
            onReviseChapter={
              onReviseChapter
                ? (name) => {
                    setReviseText('')
                    setRevisingChapter(name)
                  }
                : undefined
            }
          />
        </ResizablePanel>
      </ResizablePanelGroup>

      {/* The chapter-revision dialog (M5b): one instruction, scoped
          to the chapter the user pointed at — no inference. */}
      {revisingChapter !== null ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
          onClick={() => setRevisingChapter(null)}
        >
          <div
            className="w-[min(90vw,480px)] rounded-xl border border-border bg-background p-5 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="studio-voice text-base">
              Revise “{revisingChapter}”
            </h3>
            <p className="mt-1 text-xs text-muted-foreground">
              The studio re-plans just this chapter against your app.
              You'll review the new storyboard before anything is
              re-recorded — the rest of the film stays untouched, and
              your current cut is kept as a version.
            </p>
            <textarea
              autoFocus
              value={reviseText}
              onChange={(e) => setReviseText(e.target.value)}
              placeholder={'What should change? — "add a step showing the attachments filter", "tighten this to two scenes"…'}
              rows={3}
              className="mt-3 w-full resize-none rounded-md border border-input bg-background px-2.5 py-2 text-sm placeholder:text-muted-foreground/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
            <div className="mt-3 flex justify-end gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setRevisingChapter(null)}
              >
                Cancel
              </Button>
              <Button
                size="sm"
                disabled={!reviseText.trim()}
                onClick={() => {
                  onReviseChapter?.(revisingChapter, reviseText.trim())
                  setRevisingChapter(null)
                }}
              >
                Re-plan this chapter
              </Button>
            </div>
          </div>
        </div>
      ) : null}
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
