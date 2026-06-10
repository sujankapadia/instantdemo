import { useMemo, useState } from 'react'
import { Loader2, Play, Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { IntentEditor } from './IntentEditor'
import { emptyIntent, type Intent } from '@/api/runs'
import type { ScreenInfo } from '@/api/project'

interface IntentConfirmCardProps {
  /** Phase 1's proposed intent (from /api/project phases.1). */
  proposal: Intent
  /** What the user typed into the New Project form (intent.json). */
  userIntent?: Intent | null
  screens?: ScreenInfo[] | null
  warnings?: string[] | null
  busy?: boolean
  onConfirm: (intent: Intent) => void
}

/**
 * The intent-confirmation step of the two-run cold-start flow (M1).
 * Phase 1 explored the app and proposed a demo; the user confirms or
 * edits, then phases 2-6 run with the confirmed intent. Per-field
 * merge rule: the user's own words win; the proposal fills blanks.
 */
export function IntentConfirmCard({
  proposal,
  userIntent,
  screens,
  warnings,
  busy,
  onConfirm,
}: IntentConfirmCardProps) {
  const merged = useMemo(
    () => mergeIntent(userIntent ?? null, proposal),
    [userIntent, proposal],
  )
  const [intent, setIntent] = useState<Intent>(merged)

  return (
    <section className="border-b border-border bg-secondary/20 px-6 py-4">
      <div className="mx-auto flex max-w-3xl flex-col gap-3">
        <div className="flex items-center gap-2">
          <Sparkles className="size-4 text-primary" />
          <h2 className="text-sm font-semibold">
            Here's what I found — confirm the demo plan
          </h2>
        </div>

        {screens && screens.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {screens.map((screen) => (
              <span
                key={screen.name}
                className="rounded-full border border-border bg-background px-2 py-0.5 text-xs text-muted-foreground"
                title={screen.notes ?? undefined}
              >
                {screen.name}
                {screen.route ? (
                  <span className="ml-1 opacity-60">{screen.route}</span>
                ) : null}
              </span>
            ))}
          </div>
        )}

        {warnings && warnings.length > 0 && (
          <ul className="flex list-disc flex-col gap-0.5 pl-5 text-xs text-amber-700 dark:text-amber-400">
            {warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        )}

        <IntentEditor value={intent} onChange={setIntent} disabled={busy} />

        <div className="flex justify-end">
          <Button
            onClick={() => onConfirm(sanitize(intent))}
            disabled={busy || !intent.goal.trim()}
          >
            {busy ? (
              <>
                <Loader2 className="size-4 animate-spin" />
                Generating…
              </>
            ) : (
              <>
                <Play className="size-4" />
                Looks right — generate the demo
              </>
            )}
          </Button>
        </div>
      </div>
    </section>
  )
}

function mergeIntent(user: Intent | null, proposal: Intent): Intent {
  const base = user ?? emptyIntent()
  return {
    goal: base.goal.trim() || proposal.goal,
    audience: base.audience ?? proposal.audience,
    tone: base.tone ?? proposal.tone,
    length: base.length ?? proposal.length,
    focus: base.focus.length > 0 ? base.focus : proposal.focus,
    excludes: base.excludes.length > 0 ? base.excludes : proposal.excludes,
    addenda: base.addenda.length > 0 ? base.addenda : proposal.addenda,
  }
}

function sanitize(intent: Intent): Intent {
  const cleanList = (items: string[]) =>
    items.map((s) => s.trim()).filter((s) => s.length > 0)
  return {
    ...intent,
    goal: intent.goal.trim(),
    audience: intent.audience?.trim() || null,
    tone: intent.tone?.trim() || null,
    length: intent.length?.trim() || null,
    focus: cleanList(intent.focus),
    excludes: cleanList(intent.excludes),
    addenda: cleanList(intent.addenda),
  }
}
