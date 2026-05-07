import { Film } from 'lucide-react'

export function RightPane() {
  return (
    <aside className="flex h-full min-h-0 flex-col">
      <div className="flex flex-1 items-center justify-center border-b border-border bg-muted/10 p-4">
        <div className="flex aspect-video w-full max-w-md flex-col items-center justify-center gap-2 rounded-md border border-dashed border-border bg-muted/30 text-muted-foreground">
          <Film className="size-8 opacity-60" />
          <span className="text-sm">Video preview</span>
        </div>
      </div>
      <div className="flex h-64 shrink-0 flex-col">
        <div className="flex h-9 shrink-0 items-center border-b border-border bg-muted/30 px-4">
          <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Segments
          </span>
        </div>
        <div className="flex flex-1 items-center justify-center p-4 text-center">
          <p className="text-sm text-muted-foreground">
            Segments will appear here once a script has been generated.
          </p>
        </div>
      </div>
    </aside>
  )
}
