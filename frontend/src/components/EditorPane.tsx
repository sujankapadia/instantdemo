import type { PhaseInfo } from './PhaseRail'

interface EditorPaneProps {
  phase: PhaseInfo
}

export function EditorPane({ phase }: EditorPaneProps) {
  return (
    <section className="flex h-full min-h-0 flex-col border-r border-border">
      <div className="flex h-9 shrink-0 items-center border-b border-border bg-muted/30 px-4">
        <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Phase {phase.num} — {phase.name}
        </span>
      </div>
      <div className="flex flex-1 items-center justify-center p-8 text-center">
        <p className="max-w-md text-sm text-muted-foreground">
          Phase {phase.num} artifact will appear here.
        </p>
      </div>
    </section>
  )
}
