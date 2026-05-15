import { useState } from 'react'
import { CheckCircle2, ChevronDown, OctagonAlert } from 'lucide-react'
import { cn } from '@/lib/utils'
import { MarkdownView } from './markdown/MarkdownView'

interface ValidationViewProps {
  content: string
}

interface ParsedValidation {
  status: 'passed' | 'blocked' | 'unknown'
  reason: string | null
  body: string
}

function parseValidation(content: string): ParsedValidation {
  const blockedMatch = /^RENDER_BLOCKED:\s*(.+)\s*$/m.exec(content)
  if (blockedMatch) {
    const body = content.replace(blockedMatch[0], '').trim()
    return { status: 'blocked', reason: blockedMatch[1] ?? '', body }
  }
  const okMatch = /^RENDER_OK\s*$/m.exec(content)
  if (okMatch) {
    const body = content.replace(okMatch[0], '').trim()
    return { status: 'passed', reason: null, body }
  }
  return { status: 'unknown', reason: null, body: content }
}

export function ValidationView({ content }: ValidationViewProps) {
  const parsed = parseValidation(content)
  // Body is collapsed by default on success — the report is mostly a wall
  // of "✓ ✓ ✓" and not useful when everything worked. Expanded by default
  // on failure so the user sees what's wrong without an extra click.
  const [showDetails, setShowDetails] = useState(parsed.status !== 'passed')

  return (
    <div className="flex h-full min-h-0 flex-col overflow-auto">
      <div className="p-6 pb-0">
        <StatusBanner status={parsed.status} reason={parsed.reason} />
      </div>

      {parsed.body ? (
        <>
          <button
            type="button"
            onClick={() => setShowDetails((v) => !v)}
            className="mt-4 mb-1 ml-6 flex items-center gap-1.5 self-start rounded-md px-2 py-1 text-xs font-medium uppercase tracking-wide text-muted-foreground transition-colors hover:bg-secondary/50 hover:text-foreground cursor-pointer"
          >
            <ChevronDown
              className={cn(
                'size-3.5 transition-transform duration-200',
                showDetails ? '' : '-rotate-90',
              )}
            />
            {showDetails ? 'Hide validation details' : 'Show validation details'}
          </button>
          {showDetails ? (
            <div className="flex-1 min-h-0">
              <MarkdownView content={parsed.body} />
            </div>
          ) : null}
        </>
      ) : null}
    </div>
  )
}

function StatusBanner({
  status,
  reason,
}: {
  status: ParsedValidation['status']
  reason: string | null
}) {
  if (status === 'passed') {
    return (
      <div className="flex items-start gap-3 rounded-md border border-emerald-500/30 bg-emerald-500/10 p-4">
        <CheckCircle2 className="size-5 shrink-0 text-emerald-400" />
        <div className="space-y-0.5">
          <p className="text-sm font-medium text-emerald-300">
            Validation passed
          </p>
          <p className="text-xs text-muted-foreground">
            All checks succeeded; the renderer was invoked and produced the
            video.
          </p>
        </div>
      </div>
    )
  }
  if (status === 'blocked') {
    return (
      <div className="flex items-start gap-3 rounded-md border border-destructive/40 bg-destructive/10 p-4">
        <OctagonAlert className="size-5 shrink-0 text-destructive" />
        <div className="space-y-1">
          <p className="text-sm font-medium text-destructive">
            Validation blocked — render did not run
          </p>
          {reason ? (
            <p className="font-mono text-xs text-destructive/90">{reason}</p>
          ) : null}
          <p className="text-xs text-muted-foreground">
            See details below to understand which check failed. To recover,
            re-run an upstream phase (typically Phase 3) with a hint, or
            edit <code className="rounded bg-muted px-1 py-0.5">demo-script.json</code> directly.
          </p>
        </div>
      </div>
    )
  }
  return (
    <div className="flex items-start gap-3 rounded-md border border-border bg-muted/40 p-4">
      <CheckCircle2 className="size-5 shrink-0 text-muted-foreground" />
      <div className="space-y-0.5">
        <p className="text-sm font-medium text-foreground">Validation report</p>
        <p className="text-xs text-muted-foreground">
          The agent did not emit a RENDER_OK / RENDER_BLOCKED directive.
          Review the report below.
        </p>
      </div>
    </div>
  )
}
