import { useState } from 'react'
import { ChevronUp, Terminal } from 'lucide-react'
import { Collapsible, CollapsibleContent } from '@/components/ui/collapsible'
import { cn } from '@/lib/utils'

export function LogDrawer() {
  const [open, setOpen] = useState(false)
  return (
    <Collapsible
      open={open}
      onOpenChange={setOpen}
      className="border-t border-border bg-background"
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex h-9 w-full items-center justify-between px-4 text-left text-xs font-medium uppercase tracking-wide text-muted-foreground hover:text-foreground cursor-pointer"
      >
        <span className="flex items-center gap-2">
          <Terminal className="size-3.5" />
          Agent log
        </span>
        <ChevronUp
          className={cn(
            'size-4 transition-transform duration-200',
            open ? 'rotate-180' : '',
          )}
        />
      </button>
      <CollapsibleContent className="overflow-hidden">
        <div className="h-48 border-t border-border p-4 font-mono text-xs text-muted-foreground">
          Agent log will stream here during phase runs.
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}
