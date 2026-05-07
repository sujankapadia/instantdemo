import { Loader2 } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkBreaks from 'remark-breaks'
import CodeMirror from '@uiw/react-codemirror'
import { json as jsonLang } from '@codemirror/lang-json'
import { oneDark } from '@codemirror/theme-one-dark'
import type { PhaseInfo } from './PhaseRail'
import { useArtifact } from '@/hooks/useArtifact'
import type { PhaseNumber } from '@/api/project'

interface EditorPaneProps {
  phase: PhaseInfo
  empty?: boolean
  projectDir?: string
}

export function EditorPane({ phase, empty, projectDir }: EditorPaneProps) {
  if (empty) {
    return <EmptyProjectPane projectDir={projectDir} />
  }
  return <ArtifactView phase={phase} />
}

function EmptyProjectPane({ projectDir }: { projectDir?: string }) {
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
            Run{' '}
            <code className="rounded bg-muted px-1 py-0.5 text-xs">
              instantdemo generate
            </code>{' '}
            to create a demo for this project.
          </p>
        </div>
      </div>
    </section>
  )
}

function ArtifactView({ phase }: { phase: PhaseInfo }) {
  const result = useArtifact(phase.num as PhaseNumber)

  return (
    <section className="flex h-full min-h-0 flex-col border-r border-border">
      <div className="flex h-9 shrink-0 items-center border-b border-border bg-muted/30 px-4">
        <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Phase {phase.num} — {phase.name}
        </span>
      </div>
      <div className="flex-1 min-h-0 overflow-auto">
        {result.status === 'loading' && <LoadingState />}
        {result.status === 'error' && <ErrorState message={result.error} />}
        {result.status === 'success' && !result.data.exists && (
          <NotRunYet phaseNum={phase.num} phaseName={phase.name} />
        )}
        {result.status === 'success' && result.data.exists && (
          <ArtifactBody
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

function NotRunYet({ phaseNum, phaseName }: { phaseNum: number; phaseName: string }) {
  return (
    <div className="flex h-full items-center justify-center p-8 text-center">
      <p className="max-w-md text-sm text-muted-foreground">
        Phase {phaseNum} ({phaseName}) hasn't run yet. Its artifact will
        appear here once it has.
      </p>
    </div>
  )
}

function ArtifactBody({
  format,
  content,
}: {
  format: 'markdown' | 'json'
  content: string
}) {
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
  return (
    <article
      className={[
        'prose prose-invert max-w-none p-6',
        // Looser rhythm for the structured-segment markdown produced by
        // Phase 2; defaults are too tight for ### + bold-label content.
        'prose-headings:mt-8 prose-headings:mb-3',
        'prose-h1:text-2xl prose-h2:text-xl prose-h3:text-base prose-h3:font-semibold',
        'prose-hr:my-6 prose-hr:border-border',
        'prose-strong:text-foreground prose-strong:font-semibold',
        'prose-code:bg-muted prose-code:px-1 prose-code:py-0.5 prose-code:rounded',
        'prose-code:text-foreground prose-code:before:content-none prose-code:after:content-none',
        'prose-p:my-2',
      ].join(' ')}
    >
      <ReactMarkdown remarkPlugins={[remarkBreaks]}>{content}</ReactMarkdown>
    </article>
  )
}
