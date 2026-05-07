import { useState } from 'react'
import { Header } from './Header'
import { PhaseRail, type PhaseInfo } from './PhaseRail'
import { EditorPane } from './EditorPane'
import { RightPane } from './RightPane'
import { LogDrawer } from './LogDrawer'

const PLACEHOLDER_PHASES: PhaseInfo[] = [
  { num: 1, name: 'Analyze', status: 'completed' },
  { num: 2, name: 'Narrate', status: 'completed' },
  { num: 3, name: 'Gather', status: 'completed' },
  { num: 4, name: 'Script', status: 'completed' },
  { num: 5, name: 'Validate', status: 'completed' },
]

export function Layout() {
  const [selected, setSelected] = useState<number>(1)
  const phase =
    PLACEHOLDER_PHASES.find((p) => p.num === selected) ??
    PLACEHOLDER_PHASES[0]

  return (
    <div className="grid h-screen grid-rows-[auto_auto_minmax(0,1fr)_auto] bg-background text-foreground">
      <Header projectName="claude-code-analytics" />
      <PhaseRail
        phases={PLACEHOLDER_PHASES}
        selected={selected}
        onSelect={setSelected}
      />
      <main className="flex min-h-0">
        <div className="flex-[3] min-w-0">
          <EditorPane phase={phase} />
        </div>
        <div className="flex-[2] min-w-0">
          <RightPane />
        </div>
      </main>
      <LogDrawer />
    </div>
  )
}
