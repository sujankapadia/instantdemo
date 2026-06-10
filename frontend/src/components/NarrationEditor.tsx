import { useEffect, useRef, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'

/**
 * Inline narration editor — extracted verbatim from SegmentsList's
 * SegmentEditor (M2) so the storyboard gate and the post-render
 * segments list share one editing surface.
 */
export function NarrationEditor({
  initialNarration,
  busyExternal = false,
  error,
  onSave,
  onCancel,
}: {
  initialNarration: string
  /** External busy signal (e.g. audio re-render in flight). */
  busyExternal?: boolean
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
    if (saving || busyExternal || !text.trim()) return
    setSaving(true)
    try {
      await onSave(text.trim())
    } finally {
      setSaving(false)
    }
  }

  const busy = saving || busyExternal
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
