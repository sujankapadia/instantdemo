import { Settings } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface HeaderProps {
  projectName: string
  url?: string | null
  loading?: boolean
}

export function Header({ projectName, url, loading }: HeaderProps) {
  return (
    <header className="flex h-14 items-center justify-between border-b border-border bg-background px-4">
      <div className="flex items-baseline gap-3">
        <span className="text-base font-semibold">InstantDemo</span>
        {loading ? (
          <span className="text-sm text-muted-foreground">Loading…</span>
        ) : (
          <>
            <span className="text-sm text-muted-foreground">{projectName}</span>
            {url ? (
              <span className="text-xs text-muted-foreground/70">{url}</span>
            ) : null}
          </>
        )}
      </div>
      <Button variant="ghost" size="icon" aria-label="Settings">
        <Settings />
      </Button>
    </header>
  )
}
