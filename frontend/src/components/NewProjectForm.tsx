import { useState } from 'react'
import { Loader2, Play } from 'lucide-react'
import { Button } from '@/components/ui/button'

export interface NewProjectInputs {
  url: string
  describe: string
  source: string
  tts: 'kokoro'
  pause_between_phases: boolean
}

interface NewProjectFormProps {
  defaultValues?: Partial<NewProjectInputs>
  submitting?: boolean
  onSubmit: (values: NewProjectInputs) => void
  onCancel: () => void
  /** Triggered when the form would overwrite an existing project. The
   * caller decides whether to show a confirmation; if it returns false
   * the submit is aborted. Returns true to proceed. */
  confirmOverwrite?: () => Promise<boolean>
}

export function NewProjectForm({
  defaultValues,
  submitting,
  onSubmit,
  onCancel,
  confirmOverwrite,
}: NewProjectFormProps) {
  const [url, setUrl] = useState(defaultValues?.url ?? '')
  const [describe, setDescribe] = useState(defaultValues?.describe ?? '')
  const [source, setSource] = useState(defaultValues?.source ?? '')
  const [pauseBetweenPhases, setPauseBetweenPhases] = useState(
    defaultValues?.pause_between_phases ?? false,
  )
  const [submitInFlight, setSubmitInFlight] = useState(false)

  const isWorking = submitting || submitInFlight

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

    onSubmit({
      url: url.trim(),
      describe: describe.trim(),
      source: source.trim(),
      tts: 'kokoro',
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
          The live URL where your app is running. The agent will visit this
          to find selectors and validate the demo.
        </p>
      </div>

      <div className="flex flex-col gap-1.5">
        <label htmlFor="np-source" className="text-sm font-medium">
          Source directory{' '}
          <span className="text-muted-foreground">(recommended)</span>
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
          Absolute path to your app's source code. The agent reads this in
          Phase 1 to understand routes, components, and navigation. Leave
          blank to skip — the agent will guess from the live app only,
          which produces lower-quality results.
        </p>
      </div>

      <div className="flex flex-col gap-1.5">
        <label htmlFor="np-describe" className="text-sm font-medium">
          What to demo <span className="text-muted-foreground">(optional)</span>
        </label>
        <textarea
          id="np-describe"
          rows={3}
          value={describe}
          onChange={(e) => setDescribe(e.target.value)}
          placeholder="Show the bookmarks page and how a user can save a message from a session…"
          disabled={isWorking}
          className="rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50 resize-y"
        />
        <p className="text-xs text-muted-foreground">
          Free-form description of the flow you want demoed. Leave blank to
          let the agent pick.
        </p>
      </div>

      <div className="flex flex-col gap-1.5">
        <label className="text-sm font-medium">TTS provider</label>
        <div className="rounded-md border border-input bg-secondary/30 px-3 py-2 text-sm text-muted-foreground">
          Kokoro <span className="text-xs">(local, bundled)</span>
        </div>
        <p className="text-xs text-muted-foreground">
          Other providers (Google, ElevenLabs, Piper) require additional
          setup and aren't yet wired into this form.
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
