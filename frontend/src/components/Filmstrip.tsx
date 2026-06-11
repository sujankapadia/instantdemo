import { useEffect, useMemo, useRef, useState } from 'react'
import { Camera } from 'lucide-react'
import { FadeImg } from './FadeImg'
import { fetchExplorationShots } from '@/api/project'

interface FilmstripProps {
  /** Live screenshots streamed over SSE during Phase 1 (useRun). */
  live: { file: string; url: string }[]
  /** True while a run is actively exploring — shows the hint line. */
  exploring: boolean
}

/**
 * Horizontal strip of Phase 1 exploration screenshots (M1). The user
 * watches the agent's view of the app assemble while exploration
 * runs. Live SSE shots are merged with the on-disk listing fetched on
 * mount, so a page reload still shows the strip.
 */
export function Filmstrip({ live, exploring }: FilmstripProps) {
  const [persisted, setPersisted] = useState<string[]>([])
  const scrollerRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    let stale = false
    fetchExplorationShots()
      .then((res) => {
        if (!stale) setPersisted(res.files)
      })
      .catch(() => {
        /* endpoint missing/empty — strip just renders live shots */
      })
    return () => {
      stale = true
    }
  }, [])

  const shots = useMemo(() => {
    const byFile = new Map<string, string>()
    for (const file of persisted) {
      byFile.set(file, `/api/project/exploration/${file}`)
    }
    for (const shot of live) {
      byFile.set(shot.file, shot.url)
    }
    return [...byFile.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([file, url]) => ({ file, url }))
  }, [persisted, live])

  // Newest shot scrolls into view as it streams in.
  useEffect(() => {
    const el = scrollerRef.current
    if (el) el.scrollLeft = el.scrollWidth
  }, [shots.length])

  if (shots.length === 0 && !exploring) return null

  return (
    <div className="flex h-full flex-col gap-2 p-4">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Camera className="h-4 w-4" />
        {exploring
          ? 'Exploring your app — screens appear as they’re visited'
          : `Exploration screenshots (${shots.length})`}
      </div>
      <div
        ref={scrollerRef}
        className="flex flex-1 items-start gap-3 overflow-x-auto pb-2"
      >
        {shots.map((shot) => (
          <figure key={shot.file} className="shrink-0">
            <FadeImg
              src={shot.url}
              alt={shot.file}
              className="h-40 rounded-md border border-border object-cover shadow-sm transition-transform hover:-translate-y-0.5"
              loading="lazy"
            />
            <figcaption className="mt-1 max-w-56 truncate text-xs text-muted-foreground">
              {labelFor(shot.file)}
            </figcaption>
          </figure>
        ))}
        {exploring && (
          <div className="flex h-40 w-56 shrink-0 animate-pulse items-center justify-center rounded-md border border-dashed border-border text-xs text-muted-foreground">
            exploring…
          </div>
        )}
      </div>
    </div>
  )
}

function labelFor(file: string): string {
  return file
    .replace(/^\d+[-_]?/, '')
    .replace(/\.png$/, '')
    .replace(/[-_]/g, ' ')
}
