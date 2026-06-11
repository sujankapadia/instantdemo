import { useEffect, useState } from 'react'
import {
  CheckCircle2,
  ChevronRight,
  Clapperboard,
  Loader2,
  TriangleAlert,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { emptyIntent } from '@/api/runs'
import { runPreflight, type PreflightResponse } from '@/api/project'
import type { NewProjectInputs } from '../NewProjectForm'

type PreflightState =
  | { status: 'idle' }
  | { status: 'checking' }
  | { status: 'done'; result: PreflightResponse; checkedUrl: string }

const BRIEF_GHOST =
  '"This is for prospective customers — not technical. Friendly tone. ' +
  'Focus on the export flow; skip settings. Never show real customer names."'

interface StageEmptyProps {
  projectDir?: string | null
  submitting: boolean
  onSubmit: (values: NewProjectInputs) => void
}

/**
 * The front door (DESIGN.md principles 3 + 17): the most-designed
 * screen in the app. One hero URL field; the pre-flight echo ("I see
 * it"); ONE brief box that welcomes everything the user already
 * knows; background inputs tucked behind a disclosure. One tally-
 * accent button.
 */
export function StageEmpty({
  projectDir,
  submitting,
  onSubmit,
}: StageEmptyProps) {
  const [url, setUrl] = useState('')
  const [brief, setBrief] = useState('')
  const [source, setSource] = useState('')
  const [docs, setDocs] = useState('')
  const [preflight, setPreflight] = useState<PreflightState>({
    status: 'idle',
  })

  // Debounced pre-flight as the user types — show the app before
  // asking anything else. Soft gate: failures warn, never block.
  useEffect(() => {
    const trimmed = url.trim()
    if (!/^https?:\/\/.+/.test(trimmed)) {
      setPreflight({ status: 'idle' })
      return
    }
    const controller = new AbortController()
    const timer = setTimeout(() => {
      setPreflight({ status: 'checking' })
      runPreflight(trimmed, controller.signal)
        .then((result) =>
          setPreflight({ status: 'done', result, checkedUrl: trimmed }),
        )
        .catch((err) => {
          if (controller.signal.aborted) return
          setPreflight({
            status: 'done',
            checkedUrl: trimmed,
            result: {
              ok: false,
              screenshot: false,
              error: err instanceof Error ? err.message : 'check failed',
            },
          })
        })
    }, 600)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [url])

  const canStart = /^https?:\/\/.+/.test(url.trim()) && !submitting

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!canStart) return
    onSubmit({
      url: url.trim(),
      source: source.trim(),
      docs: docs.trim(),
      intent: { ...emptyIntent(), goal: brief.trim() },
      pause_between_phases: false,
    })
  }

  return (
    <div className="flex h-full w-full flex-1 items-center justify-center overflow-y-auto px-6">
      <form
        onSubmit={handleSubmit}
        className="flex w-full max-w-xl flex-col gap-5 py-10"
      >
        <div className="flex flex-col items-center gap-2 text-center">
          <Clapperboard className="size-8 text-primary" />
          <h1 className="text-2xl font-semibold tracking-tight">
            Let's film your app
          </h1>
          <p className="text-sm text-muted-foreground">
            Point me at it — I'll watch it work, storyboard a demo,
            and narrate the film.
          </p>
        </div>

        <div className="flex flex-col gap-2">
          <input
            type="url"
            autoFocus
            required
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="http://localhost:3000"
            disabled={submitting}
            aria-label="Your app's address"
            className="rounded-lg border border-input bg-background px-4 py-3 text-base placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
          />
          {preflight.status === 'checking' && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Loader2 className="size-3 animate-spin" />
              Looking at your app…
            </div>
          )}
          {preflight.status === 'done' && preflight.result.ok && (
            <div className="flex items-start gap-3 rounded-md border border-border bg-secondary/20 p-2">
              <img
                src={`/api/preflight/screenshot?v=${encodeURIComponent(preflight.checkedUrl)}`}
                alt="Your app"
                className="h-16 rounded border border-border object-cover"
              />
              <div className="flex flex-col gap-0.5 text-xs">
                <span className="flex items-center gap-1 font-medium text-status-ok">
                  <CheckCircle2 className="size-3.5" /> I see it
                </span>
                {preflight.result.title && (
                  <span className="text-muted-foreground">
                    “{preflight.result.title}”
                  </span>
                )}
              </div>
            </div>
          )}
          {preflight.status === 'done' && !preflight.result.ok && (
            <div className="flex items-start gap-2 rounded-md border border-status-warn/40 bg-status-warn/10 p-2 text-xs text-status-warn">
              <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
              <span>
                {preflight.result.error} You can still start — I'll keep
                trying while exploring.
              </span>
            </div>
          )}
        </div>

        <div className="flex flex-col gap-1.5">
          <textarea
            rows={4}
            value={brief}
            onChange={(e) => setBrief(e.target.value)}
            placeholder={BRIEF_GHOST}
            disabled={submitting}
            aria-label="Your brief"
            className="studio-voice rounded-lg border border-input bg-background px-4 py-3 placeholder:text-muted-foreground/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
          />
          <p className="text-xs text-muted-foreground">
            Mention anything you know: who it's for, the tone, what to
            show or skip — a line or a paragraph.
          </p>
        </div>

        <Collapsible>
          <CollapsibleTrigger className="group flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
            <ChevronRight className="size-3.5 transition-transform group-data-[state=open]:rotate-90" />
            Add background
          </CollapsibleTrigger>
          <CollapsibleContent className="flex flex-col gap-3 pt-3">
            <div className="flex flex-col gap-1">
              <label
                htmlFor="se-docs"
                className="text-xs font-medium text-muted-foreground"
              >
                Product notes
              </label>
              <textarea
                id="se-docs"
                rows={3}
                value={docs}
                onChange={(e) => setDocs(e.target.value)}
                placeholder="Paste a product one-pager or README excerpt…"
                disabled={submitting}
                className="rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label
                htmlFor="se-source"
                className="text-xs font-medium text-muted-foreground"
              >
                Source code folder
              </label>
              <input
                id="se-source"
                type="text"
                value={source}
                onChange={(e) => setSource(e.target.value)}
                placeholder="/path/to/your/codebase (optional)"
                disabled={submitting}
                spellCheck={false}
                className="rounded-md border border-input bg-background px-3 py-2 font-mono text-xs placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
              />
            </div>
          </CollapsibleContent>
        </Collapsible>

        <Button type="submit" size="lg" disabled={!canStart} className="w-full">
          {submitting ? (
            <>
              <Loader2 className="size-4 animate-spin" />
              Starting…
            </>
          ) : (
            'Make my demo'
          )}
        </Button>

        {projectDir ? (
          <p className="text-center font-mono text-[10px] text-muted-foreground/60">
            {projectDir}
          </p>
        ) : null}
      </form>
    </div>
  )
}
