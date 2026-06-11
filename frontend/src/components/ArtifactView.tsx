import { Loader2 } from 'lucide-react'
import CodeMirror from '@uiw/react-codemirror'
import { json as jsonLang } from '@codemirror/lang-json'
import { oneDark } from '@codemirror/theme-one-dark'
import type { PhaseInfo } from './PhaseRail'
import { MarkdownView } from './markdown/MarkdownView'
import { PhaseDriftNotice } from './PhaseDriftNotice'
import { ValidationView } from './ValidationView'
import { useArtifact } from '@/hooks/useArtifact'
import type { PhaseNumber } from '@/api/project'

// The per-phase artifact reader — Inspector-only since the
// one-object pass (the old EditorPane shell and its empty-state
// onboarding died with the front-door StageEmpty).
export function ArtifactView({ phase }: { phase: PhaseInfo }) {
  const result = useArtifact(phase.num as PhaseNumber)

  return (
    <section className="flex h-full min-h-0 flex-col border-r border-border">
      <div className="flex h-9 shrink-0 items-center border-b border-border bg-muted/30 px-4">
        <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {phase.num} · {phase.name}
        </span>
      </div>
      <div className="flex-1 min-h-0 overflow-auto">
        {result.status === 'loading' && <LoadingState />}
        {result.status === 'error' && <ErrorState message={result.error} />}
        {result.status === 'success' && !result.data.exists && (
          <NotRunYet phaseName={phase.name} />
        )}
        {result.status === 'success' && result.data.exists && (
          <ArtifactBody
            phase={phase}
            format={result.data.format}
            content={result.data.content ?? ''}
          />
        )}
      </div>
    </section>
  )
}

function LoadingState() {
  return (
    <div className="flex h-full items-center justify-center text-muted-foreground">
      <Loader2 className="size-4 animate-spin" />
      <span className="ml-2 text-sm">Loading…</span>
    </div>
  )
}

function ErrorState({ message }: { message: string }) {
  return (
    <div className="flex h-full items-center justify-center p-6 text-center">
      <p className="text-sm text-destructive">Failed to load: {message}</p>
    </div>
  )
}

function NotRunYet({ phaseName }: { phaseName: string }) {
  return (
    <div className="flex h-full items-center justify-center p-8 text-center">
      <p className="max-w-md text-sm text-muted-foreground">
        {phaseName} hasn't run yet — its artifact will appear here once
        it has.
      </p>
    </div>
  )
}

interface ArtifactBodyProps {
  phase: PhaseInfo
  format: 'markdown' | 'json'
  content: string
}

function ArtifactBody({ phase, format, content }: ArtifactBodyProps) {
  if (format === 'json') {
    return (
      <CodeMirror
        value={content}
        theme={oneDark}
        extensions={[jsonLang()]}
        editable={false}
        readOnly
        basicSetup={{
          lineNumbers: true,
          foldGutter: true,
          highlightActiveLine: false,
          highlightActiveLineGutter: false,
          autocompletion: false,
        }}
        className="h-full text-sm"
        height="100%"
      />
    )
  }
  if (phase.num === 5) {
    return <ValidationView content={content} />
  }
  if (phase.num === 2 || phase.num === 3) {
    return (
      <div className="flex h-full flex-col">
        <PhaseDriftNotice phaseNumber={phase.num} />
        <div className="flex-1 min-h-0 overflow-auto">
          <MarkdownView content={content} />
        </div>
      </div>
    )
  }
  return <MarkdownView content={content} />
}
