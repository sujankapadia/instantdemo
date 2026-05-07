import type { PhaseInfo } from './PhaseRail'

interface EditorPaneProps {
  phase: PhaseInfo
  empty?: boolean
  projectDir?: string
}

export function EditorPane({ phase, empty, projectDir }: EditorPaneProps) {
  if (empty) {
    return (
      <section className="flex h-full min-h-0 flex-col border-r border-border">
        <div className="flex h-9 shrink-0 items-center border-b border-border bg-muted/30 px-4">
          <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            No project here yet
          </span>
        </div>
        <div className="flex flex-1 items-center justify-center p-8 text-center">
          <div className="max-w-md space-y-2">
            <p className="text-sm text-foreground">
              No InstantDemo project found in this directory.
            </p>
            {projectDir ? (
              <p className="font-mono text-xs text-muted-foreground">{projectDir}</p>
            ) : null}
            <p className="text-sm text-muted-foreground">
              Run <code className="rounded bg-muted px-1 py-0.5 text-xs">instantdemo generate</code> to create a demo for this project.
            </p>
          </div>
        </div>
      </section>
    )
  }

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
