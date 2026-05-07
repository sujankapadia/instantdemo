import { Settings } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface HeaderProps {
  projectName: string
}

export function Header({ projectName }: HeaderProps) {
  return (
    <header className="flex h-14 items-center justify-between border-b border-border bg-background px-4">
      <div className="flex items-baseline gap-3">
        <span className="text-base font-semibold">InstantDemo</span>
        <span className="text-sm text-muted-foreground">{projectName}</span>
      </div>
      <Button variant="ghost" size="icon" aria-label="Settings">
        <Settings />
      </Button>
    </header>
  )
}
