import { AlertTriangle, FileText, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import type { ExploreFindings, ExploreSegmentFinding } from '@/api/project'

interface Phase4TriagePanelProps {
  findings: ExploreFindings
  /** Triggered by "Regenerate" — typically opens the New Project /
   *  Regenerate modal with current intent prefilled. */
  onRegenerate: () => void
  /** Triggered by "View full report" — typically opens the Phase 4
   *  artifact in the editor pane. */
  onViewReport: () => void
}

/**
 * Surfaces Phase 4 (Explore) failures with humanized suggestions.
 * Only renders when there are blocking failures — the parent decides
 * to mount or skip based on `explore_overall === 'BLOCKED'`.
 *
 * See issue #48.
 */
export function Phase4TriagePanel({
  findings,
  onRegenerate,
  onViewReport,
}: Phase4TriagePanelProps) {
  const failures = (findings.segments ?? []).filter(
    (s) => s.status === 'FAIL_SELECTOR' || s.status === 'FAIL_NARRATIVE',
  )
  if (failures.length === 0) return null

  const failCount = failures.length
  const headline =
    failCount === 1
      ? 'Phase 4 found an issue that needs your attention'
      : `Phase 4 found ${failCount} issues that need your attention`

  return (
    <div className="border-b border-amber-500/30 bg-amber-500/5 px-6 py-4">
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 size-5 shrink-0 text-amber-500" />
        <div className="flex-1 space-y-3">
          <div className="flex items-baseline justify-between gap-4">
            <h3 className="text-sm font-semibold text-foreground">
              {headline}
            </h3>
            <span className="text-xs text-muted-foreground">
              Pipeline halted at Explore — fix and Regenerate to continue
            </span>
          </div>
          <ul className="space-y-3">
            {failures.map((f) => (
              <FailureItem key={f.index} finding={f} />
            ))}
          </ul>
          <div className="flex items-center gap-2 pt-1">
            <Button size="sm" onClick={onRegenerate}>
              <RefreshCw className="size-3.5" />
              Regenerate
            </Button>
            <Button size="sm" variant="ghost" onClick={onViewReport}>
              <FileText className="size-3.5" />
              View full report
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

function FailureItem({ finding }: { finding: ExploreSegmentFinding }) {
  const label =
    finding.status === 'FAIL_SELECTOR'
      ? 'Selector miss'
      : 'Content mismatch'
  // Primary text: the agent's user-facing suggestion (plain-language,
  // describes both what's wrong and what to do). Fall back to `reason`
  // only if no suggestion was emitted — `reason` is diagnostic and
  // technical, so we'd rather show nothing than dev-talk to an end
  // user. Technical detail lives in phase4.md (View full report).
  const primaryText = finding.suggestion?.trim() || finding.reason?.trim() || ''
  return (
    <li className="rounded-md border border-amber-500/20 bg-background/60 px-3 py-2">
      <div className="flex items-baseline gap-2">
        <span className="font-mono text-xs uppercase tracking-wide text-amber-600">
          Segment {finding.index}
        </span>
        <span className="text-xs text-muted-foreground">{label}</span>
      </div>
      {primaryText ? (
        <p className="mt-1 text-sm text-foreground/90">{primaryText}</p>
      ) : null}
    </li>
  )
}
