import { Children, isValidElement, type ReactElement, type ReactNode } from 'react'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkBreaks from 'remark-breaks'
import remarkGfm from 'remark-gfm'
import {
  Crosshair,
  MessageSquareQuote,
  MousePointer2,
} from 'lucide-react'
import { cn } from '@/lib/utils'

interface MarkdownViewProps {
  content: string
  className?: string
}

export function MarkdownView({ content, className }: MarkdownViewProps) {
  return (
    <article
      className={cn(
        'prose prose-invert max-w-none p-6',
        'prose-headings:mt-8 prose-headings:mb-3',
        'prose-h1:text-2xl prose-h2:text-xl prose-h3:text-base prose-h3:font-semibold',
        'prose-strong:text-foreground prose-strong:font-semibold',
        'prose-code:bg-muted prose-code:px-1 prose-code:py-0.5 prose-code:rounded',
        'prose-code:text-foreground prose-code:before:content-none prose-code:after:content-none',
        'prose-p:my-2',
        className,
      )}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkBreaks]}
        components={mdComponents}
      >
        {content}
      </ReactMarkdown>
    </article>
  )
}

// ---------------------------------------------------------------------------
// Custom element renderers
// ---------------------------------------------------------------------------

const mdComponents: Components = {
  h3({ children }) {
    return <SegmentHeading>{children}</SegmentHeading>
  },
  p({ children }) {
    return <LabeledOrPlainParagraph>{children}</LabeledOrPlainParagraph>
  },
  hr() {
    return <hr className="not-prose my-6 border-0 h-px bg-gradient-to-r from-transparent via-border to-transparent" />
  },
}

// ---------------------------------------------------------------------------
// Segment headings: "Segment N — title" → numbered badge + title row
// ---------------------------------------------------------------------------

function SegmentHeading({ children }: { children: ReactNode }) {
  const text = childrenToText(children)
  // Match "Segment 1 — The Stash" with em dash (—) or regular hyphen (-).
  const match = /^Segment\s+(\d+)\s*[—-]\s*(.+)$/.exec(text.trim())

  if (!match) {
    // Not a segment heading — let prose handle it.
    return <h3 className="mt-8 mb-3 text-base font-semibold">{children}</h3>
  }

  const num = match[1] ?? ''
  const title = match[2] ?? ''
  return (
    <div className="not-prose mt-8 mb-3 flex items-center gap-3">
      <span className="inline-flex size-7 shrink-0 items-center justify-center rounded-full bg-secondary text-xs font-mono font-semibold text-secondary-foreground">
        {num.padStart(2, '0')}
      </span>
      <h3 className="text-base font-semibold text-foreground">{title}</h3>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Labeled paragraphs: split a <p> on inner <strong>Label:</strong> nodes
// and render each label/body pair as a structured labeled row.
// ---------------------------------------------------------------------------

interface LabeledRow {
  label: string
  body: ReactNode[]
}

function LabeledOrPlainParagraph({ children }: { children: ReactNode }) {
  const childArray = Children.toArray(children)
  const rows = parseLabeledRows(childArray)
  if (rows === null || rows.length === 0) {
    return <p>{children}</p>
  }
  return (
    <div className="not-prose my-3 flex flex-col gap-2">
      {rows.map((row, i) => (
        <LabeledRowView key={i} label={row.label} body={row.body} />
      ))}
    </div>
  )
}

/**
 * Walk `children` and, if the first non-whitespace child is a <strong> whose
 * text ends with ":", split into one or more {label, body} rows. Subsequent
 * <strong>Label:</strong> nodes start new rows; <br> elements separating
 * them are dropped.
 *
 * Returns null when no leading label is found — caller should render as
 * a plain <p>.
 */
function parseLabeledRows(children: ReactNode[]): LabeledRow[] | null {
  const rows: LabeledRow[] = []
  let current: LabeledRow | null = null

  for (const child of children) {
    if (isLabelStrong(child)) {
      const labelText = childrenToText(child.props.children)
      const label = labelText.replace(/:\s*$/, '').trim()
      if (current) rows.push(current)
      current = { label, body: [] }
      continue
    }

    if (!current) {
      // No label has started; this paragraph isn't a labeled row.
      return null
    }

    if (isBrElement(child)) {
      // Skip <br>s — they separate label rows in source markdown.
      continue
    }

    if (current.body.length === 0 && typeof child === 'string') {
      // Trim a leading space that came right after the strong's colon.
      const trimmed = child.replace(/^\s+/, '')
      if (trimmed === '') continue
      current.body.push(trimmed)
      continue
    }

    current.body.push(child)
  }
  if (current) rows.push(current)
  return rows.length > 0 ? rows : null
}

function isLabelStrong(node: ReactNode): node is ReactElement<{ children: ReactNode }> {
  if (!isValidElement(node)) return false
  const props = node.props as { children?: ReactNode }
  if ((node.type as unknown) !== 'strong' && (node.type as { displayName?: string }).displayName !== 'strong') {
    // react-markdown renders <strong> as the literal HTML element by default.
    if (node.type !== 'strong') return false
  }
  const text = childrenToText(props.children).trim()
  return text.endsWith(':')
}

function isBrElement(node: ReactNode): boolean {
  return isValidElement(node) && node.type === 'br'
}

// ---------------------------------------------------------------------------
// Labeled row view: uppercase chip on left, body text on right
// ---------------------------------------------------------------------------

interface LabelMeta {
  icon: ReactElement | null
  classes: string
}

const DEFAULT_META: LabelMeta = {
  icon: null,
  classes: 'bg-secondary text-secondary-foreground',
}

function getLabelMeta(label: string): LabelMeta {
  const key = label.toLowerCase()
  if (key === 'action') {
    return {
      icon: <MousePointer2 className="size-3" />,
      classes: 'bg-sky-500/10 text-sky-300',
    }
  }
  if (key === 'narration') {
    return {
      icon: <MessageSquareQuote className="size-3" />,
      classes: 'bg-amber-500/10 text-amber-300',
    }
  }
  if (key === 'target') {
    return {
      icon: <Crosshair className="size-3" />,
      classes: 'bg-emerald-500/10 text-emerald-300',
    }
  }
  return DEFAULT_META
}

function LabeledRowView({ label, body }: LabeledRow) {
  const meta = getLabelMeta(label)
  return (
    <div className="grid grid-cols-[7.5rem_1fr] items-start gap-3">
      <div
        className={cn(
          'inline-flex items-center gap-1.5 rounded px-2 py-1 text-[11px] font-medium uppercase tracking-wide',
          meta.classes,
        )}
      >
        {meta.icon}
        {label}
      </div>
      <div className="text-sm leading-relaxed text-foreground">{body}</div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Helper: flatten a React children tree to plain text
// ---------------------------------------------------------------------------

function childrenToText(children: ReactNode): string {
  let out = ''
  Children.forEach(children, (child) => {
    if (typeof child === 'string') {
      out += child
    } else if (typeof child === 'number') {
      out += String(child)
    } else if (isValidElement(child)) {
      const props = child.props as { children?: ReactNode }
      out += childrenToText(props.children)
    }
  })
  return out
}
