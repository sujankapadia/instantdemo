import { ChevronDown, ChevronRight } from 'lucide-react'
import { useState } from 'react'
import type { Intent } from '@/api/runs'

interface IntentEditorProps {
  value: Intent
  onChange: (next: Intent) => void
  disabled?: boolean
  /** When true, advanced fields (everything except goal) start
   *  expanded. New Project starts collapsed; the future re-run
   *  dialog will start expanded. */
  advancedExpanded?: boolean
  /** Custom label for the goal field — New Project says
   *  "What to demo," other surfaces may want "Goal" etc. */
  goalLabel?: string
  goalPlaceholder?: string
  goalHelp?: string
}

/**
 * Edits an `Intent` struct. Reused by the New Project modal and
 * (later) the per-phase re-run dialog. Goal is always visible;
 * audience / tone / length / focus / excludes / addenda live
 * behind a collapsible "Style and scope" section so first-time
 * users aren't overwhelmed. See issue #39.
 */
export function IntentEditor({
  value,
  onChange,
  disabled,
  advancedExpanded,
  goalLabel = 'What to demo',
  goalPlaceholder = 'Show the bookmarks page and how a user can save a message…',
  goalHelp = 'Free-form description of the flow you want demoed. Leave blank to let the agent pick.',
}: IntentEditorProps) {
  const [advancedOpen, setAdvancedOpen] = useState(!!advancedExpanded)

  const update = (patch: Partial<Intent>) => onChange({ ...value, ...patch })

  // Focus / excludes / addenda are persisted as string arrays but
  // edited as newline-separated textareas. Convert at the boundary.
  const toLines = (items: string[]) => items.join('\n')
  // Don't trim or filter during editing — that strips spaces and
  // empty lines as the user types them. Trim + filter on form
  // submit instead (see NewProjectForm.tsx). Raw split keeps the
  // textarea behaving like a normal multi-line input.
  const fromLines = (text: string) => text.split('\n')

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <label htmlFor="intent-goal" className="text-sm font-medium">
          {goalLabel}{' '}
          <span className="text-muted-foreground">(optional)</span>
        </label>
        <textarea
          id="intent-goal"
          rows={3}
          value={value.goal}
          onChange={(e) => update({ goal: e.target.value })}
          placeholder={goalPlaceholder}
          disabled={disabled}
          className="rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50 resize-y"
        />
        <p className="text-xs text-muted-foreground">{goalHelp}</p>
      </div>

      <button
        type="button"
        onClick={() => setAdvancedOpen((v) => !v)}
        className="flex items-center gap-1.5 self-start text-sm font-medium text-muted-foreground hover:text-foreground"
      >
        {advancedOpen ? (
          <ChevronDown className="size-4" />
        ) : (
          <ChevronRight className="size-4" />
        )}
        Style and scope (optional)
      </button>

      {advancedOpen ? (
        <div className="flex flex-col gap-4 pl-5">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <FieldText
              id="intent-audience"
              label="Audience"
              value={value.audience ?? ''}
              onChange={(v) => update({ audience: v || null })}
              placeholder="technical / non-technical"
              disabled={disabled}
            />
            <FieldText
              id="intent-tone"
              label="Tone"
              value={value.tone ?? ''}
              onChange={(v) => update({ tone: v || null })}
              placeholder="casual / formal / neutral"
              disabled={disabled}
            />
            <FieldText
              id="intent-length"
              label="Length"
              value={value.length ?? ''}
              onChange={(v) => update({ length: v || null })}
              placeholder="short / medium / long"
              disabled={disabled}
            />
          </div>

          <FieldArray
            id="intent-focus"
            label="Focus"
            help="Areas to emphasize. One per line."
            value={value.focus}
            onChange={(items) => update({ focus: items })}
            disabled={disabled}
            toLines={toLines}
            fromLines={fromLines}
          />
          <FieldArray
            id="intent-excludes"
            label="Exclude"
            help="Areas to skip. One per line."
            value={value.excludes}
            onChange={(items) => update({ excludes: items })}
            disabled={disabled}
            toLines={toLines}
            fromLines={fromLines}
          />
          <FieldArray
            id="intent-addenda"
            label="Additional guidance"
            help="Free-form notes that don't fit a slot. One per line."
            value={value.addenda}
            onChange={(items) => update({ addenda: items })}
            disabled={disabled}
            toLines={toLines}
            fromLines={fromLines}
          />
        </div>
      ) : null}
    </div>
  )
}

function FieldText({
  id,
  label,
  value,
  onChange,
  placeholder,
  disabled,
}: {
  id: string
  label: string
  value: string
  onChange: (next: string) => void
  placeholder?: string
  disabled?: boolean
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-xs font-medium">
        {label}
      </label>
      <input
        id={id}
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        className="rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
      />
    </div>
  )
}

function FieldArray({
  id,
  label,
  help,
  value,
  onChange,
  disabled,
  toLines,
  fromLines,
}: {
  id: string
  label: string
  help: string
  value: string[]
  onChange: (next: string[]) => void
  disabled?: boolean
  toLines: (items: string[]) => string
  fromLines: (text: string) => string[]
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-xs font-medium">
        {label}
      </label>
      <textarea
        id={id}
        rows={2}
        value={toLines(value)}
        onChange={(e) => onChange(fromLines(e.target.value))}
        disabled={disabled}
        className="rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50 resize-y"
      />
      <p className="text-xs text-muted-foreground">{help}</p>
    </div>
  )
}
