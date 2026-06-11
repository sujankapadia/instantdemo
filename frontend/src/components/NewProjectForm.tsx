import { useEffect, useState } from 'react'
import { CheckCircle2, Loader2, Play, TriangleAlert } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { IntentEditor } from './IntentEditor'
import { emptyIntent, type Intent } from '@/api/runs'
import { runPreflight, type PreflightResponse } from '@/api/project'

export interface NewProjectInputs {
  url: string
  source: string
  intent: Intent
  docs: string
  pause_between_phases: boolean
}

type PreflightState =
  | { status: 'idle' }
  | { status: 'checking' }
  | { status: 'done'; result: PreflightResponse; checkedUrl: string }

interface NewProjectFormProps {
  defaultValues?: Partial<NewProjectInputs>
  submitting?: boolean
  onSubmit: (values: NewProjectInputs) => void
  onCancel: () => void
  /** Triggered when the form would overwrite an existing project. The
   * caller decides whether to show a confirmation; if it returns false
   * the submit is aborted. Returns true to proceed. */
  confirmOverwrite?: () => Promise<boolean>
  /** One-line description of the project's current voice (M3),
   * e.g. "Alba (stock)" or "My cloned voice". */
  voiceSummary?: string
  /** Opens the Voice & Pronunciation dialog. */
  onOpenVoiceSettings?: () => void
}

export function NewProjectForm({
  defaultValues,
  submitting,
  onSubmit,
  onCancel,
  confirmOverwrite,
  voiceSummary,
  onOpenVoiceSettings,
}: NewProjectFormProps) {
  const [url, setUrl] = useState(defaultValues?.url ?? '')
  const [source, setSource] = useState(defaultValues?.source ?? '')
  const [intent, setIntent] = useState<Intent>(
    () => defaultValues?.intent ?? emptyIntent(),
  )
  const [docs, setDocs] = useState(defaultValues?.docs ?? '')
  const [pauseBetweenPhases, setPauseBetweenPhases] = useState(
    defaultValues?.pause_between_phases ?? false,
  )
  const [submitInFlight, setSubmitInFlight] = useState(false)
  const [preflight, setPreflight] = useState<PreflightState>({
    status: 'idle',
  })

  const isWorking = submitting || submitInFlight

  // Pre-flight: debounced probe of the URL as the user types (M1).
  // Soft gate — failures warn but never block submission.
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
              error:
                err instanceof Error ? err.message : 'pre-flight failed',
            },
          })
        })
    }, 600)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [url])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (isWorking) return
    if (!url.trim()) return

    if (confirmOverwrite) {
      setSubmitInFlight(true)
      const ok = await confirmOverwrite()
      setSubmitInFlight(false)
      if (!ok) return
    }

    // Trim+filter the multi-line array fields at submit time.
    // IntentEditor keeps the raw textarea content during editing so
    // users can type spaces and blank lines without the value being
    // mutated under them. This is the one place we sanitize before
    // sending to the backend.
    const cleanList = (items: string[]) =>
      items.map((s) => s.trim()).filter((s) => s.length > 0)
    onSubmit({
      url: url.trim(),
      source: source.trim(),
      docs: docs.trim(),
      intent: {
        ...intent,
        goal: intent.goal.trim(),
        audience: intent.audience?.trim() || null,
        tone: intent.tone?.trim() || null,
        length: intent.length?.trim() || null,
        focus: cleanList(intent.focus),
        excludes: cleanList(intent.excludes),
        addenda: cleanList(intent.addenda),
      },
      pause_between_phases: pauseBetweenPhases,
    })
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <label htmlFor="np-url" className="text-sm font-medium">
          App URL
        </label>
        <input
          id="np-url"
          type="url"
          required
          autoFocus
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="http://localhost:3000"
          disabled={isWorking}
          className="rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
        />
        <p className="text-xs text-muted-foreground">
          The live URL where your app is running. The agent explores this
          to understand your app and build the demo.
        </p>
        {preflight.status === 'checking' && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="size-3 animate-spin" />
            Checking your app…
          </div>
        )}
        {preflight.status === 'done' && preflight.result.ok && (
          <div className="flex items-start gap-3 rounded-md border border-border bg-secondary/20 p-2">
            <img
              src={`/api/preflight/screenshot?v=${encodeURIComponent(preflight.checkedUrl)}`}
              alt="App preview"
              className="h-16 rounded border border-border object-cover"
            />
            <div className="flex flex-col gap-0.5 text-xs">
              <span className="flex items-center gap-1 font-medium text-green-600">
                <CheckCircle2 className="size-3.5" /> Found your app
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
          <div className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-xs text-amber-700 dark:text-amber-400">
            <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
            <span>
              {preflight.result.error} You can still continue — the agent
              retries during exploration.
            </span>
          </div>
        )}
      </div>

      <div className="flex flex-col gap-1.5">
        <label htmlFor="np-source" className="text-sm font-medium">
          Source directory{' '}
          <span className="text-muted-foreground">(optional)</span>
        </label>
        <input
          id="np-source"
          type="text"
          value={source}
          onChange={(e) => setSource(e.target.value)}
          placeholder="/path/to/your/codebase"
          disabled={isWorking}
          spellCheck={false}
          className="rounded-md border border-input bg-background px-3 py-2 font-mono text-xs placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
        />
        <p className="text-xs text-muted-foreground">
          Absolute path to your app's source code. Optional enrichment —
          the agent explores the live app either way, and may read source
          for hidden routes and exact terminology when provided.
        </p>
      </div>

      <div className="flex flex-col gap-1.5">
        <label htmlFor="np-docs" className="text-sm font-medium">
          Product context{' '}
          <span className="text-muted-foreground">(optional)</span>
        </label>
        <textarea
          id="np-docs"
          rows={3}
          value={docs}
          onChange={(e) => setDocs(e.target.value)}
          placeholder="Paste a product one-pager or README excerpt…"
          disabled={isWorking}
          className="rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
        />
        <p className="text-xs text-muted-foreground">
          Used for framing and vocabulary (what features are called, who
          it's for). The live app remains the source of truth.
        </p>
      </div>

      <IntentEditor
        value={intent}
        onChange={setIntent}
        disabled={isWorking}
      />

      <div className="flex flex-col gap-1.5">
        <label className="text-sm font-medium">Voice</label>
        <div className="flex items-center justify-between rounded-md border border-input bg-secondary/30 px-3 py-2 text-sm text-muted-foreground">
          <span>{voiceSummary ?? 'Alba (stock)'}</span>
          {onOpenVoiceSettings ? (
            <button
              type="button"
              onClick={onOpenVoiceSettings}
              className="text-xs text-primary hover:underline"
            >
              Change…
            </button>
          ) : null}
        </div>
        <p className="text-xs text-muted-foreground">
          Saved with the project — change it any time, including using
          your own voice, in Voice settings.
        </p>
      </div>

      <div className="flex items-start gap-2">
        <input
          id="np-pause"
          type="checkbox"
          checked={pauseBetweenPhases}
          onChange={(e) => setPauseBetweenPhases(e.target.checked)}
          disabled={isWorking}
          className="mt-0.5 size-4 cursor-pointer"
        />
        <div className="flex flex-col gap-0.5">
          <label
            htmlFor="np-pause"
            className="cursor-pointer text-sm font-medium"
          >
            Pause between phases
          </label>
          <p className="text-xs text-muted-foreground">
            Stops after each phase so you can review the artifact before
            continuing. Useful for inspecting the script (Phase 4) before
            committing to the render.
          </p>
        </div>
      </div>

      <div className="flex justify-end gap-2 pt-2">
        <Button
          type="button"
          variant="ghost"
          onClick={onCancel}
          disabled={isWorking}
        >
          Cancel
        </Button>
        <Button type="submit" disabled={isWorking || !url.trim()}>
          {isWorking ? (
            <>
              <Loader2 className="size-4 animate-spin" />
              Starting…
            </>
          ) : (
            <>
              <Play className="size-4" />
              Generate Demo
            </>
          )}
        </Button>
      </div>
    </form>
  )
}
