import { Loader2 } from 'lucide-react'
import { Filmstrip } from '../Filmstrip'

/**
 * The signature moment (DESIGN.md principle 10): the user watches
 * the studio watch their app. Full-width, centered, unhurried.
 */
export function StageExploring({
  screenshots,
  exploring,
}: {
  screenshots: { file: string; url: string }[]
  exploring: boolean
}) {
  return (
    <div className="flex h-full w-full flex-1 flex-col items-center justify-center gap-6 overflow-hidden px-8">
      <div className="studio-voice flex items-center gap-2.5 text-foreground/90">
        <Loader2 className="size-4 animate-spin text-primary" />
        Watching your app — screens appear as they're visited.
      </div>
      <div className="w-full max-w-5xl">
        <Filmstrip live={screenshots} exploring={exploring} />
      </div>
    </div>
  )
}
