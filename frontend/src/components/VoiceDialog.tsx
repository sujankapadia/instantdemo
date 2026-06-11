import { useRef, useState } from 'react'
import {
  AudioLines,
  Loader2,
  Mic,
  Play,
  Plus,
  Trash2,
  TriangleAlert,
  Upload,
} from 'lucide-react'
import { reRenderSegmentAudio } from '@/api/segments'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  deleteReference,
  previewVoice,
  updateVoice,
  uploadReference,
  type PronunciationRow,
  type VoiceState,
} from '@/api/voice'
import type { VoiceFetchState } from '@/hooks/useVoice'

interface VoiceDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  state: VoiceFetchState
  apply: (data: VoiceState) => void
  /** Block config writes while a run is active (server 409s anyway —
   * this just disables the controls with a hint). */
  runActive: boolean
  /** A rendered demo.mp4 exists — enables "Re-voice video". */
  videoExists: boolean
  /** Fired after a successful re-voice so the layout can refresh
   * segments + bust the video cache (the runCompleteToken signal). */
  onReVoiced: () => void
}

/**
 * Voice & Pronunciation settings (M3, #59). Three tabs: pick a stock
 * voice (instant ▶ preview), clone your own ("a voice like yours" —
 * upload + consent + A/B), and pronunciation respellings ("type it
 * like it sounds" + listen-check). Everything persists to the
 * project's tts.json, which every render and segment re-render reads.
 */
export function VoiceDialog({
  open,
  onOpenChange,
  state,
  apply,
  runActive,
  videoExists,
  onReVoiced,
}: VoiceDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Voice &amp; pronunciation</DialogTitle>
          <DialogDescription>
            How your demos sound. Saved with the project — every render
            and narration edit uses this voice.
          </DialogDescription>
        </DialogHeader>
        {state.status === 'loading' ? (
          <div className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Loading…
          </div>
        ) : state.status === 'error' ? (
          <p className="py-4 text-sm text-destructive">{state.error}</p>
        ) : (
          <>
            <VoiceDialogBody
              data={state.data}
              apply={apply}
              runActive={runActive}
            />
            {videoExists && state.data.pocket_installed ? (
              <ReVoiceBar runActive={runActive} onReVoiced={onReVoiced} />
            ) : null}
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}

/**
 * One-click "apply the current voice to the existing video" — audio
 * only, no browser re-recording (~30s). Reuses the audio-only
 * re-render endpoint, which regenerates ALL segment clips with the
 * project voice and remuxes over demo.mp4.
 */
function ReVoiceBar({
  runActive,
  onReVoiced,
}: {
  runActive: boolean
  onReVoiced: () => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)
  return (
    <div className="flex items-center justify-between gap-3 border-t border-border pt-3">
      <p className="text-xs text-muted-foreground">
        {done
          ? 'Done — the video now uses this voice.'
          : 'Apply this voice to the existing video (audio only, ~30s).'}
        {error ? (
          <span className="block text-destructive">{error}</span>
        ) : null}
      </p>
      <Button
        size="sm"
        variant="outline"
        disabled={busy || runActive}
        onClick={() => {
          setBusy(true)
          setError(null)
          setDone(false)
          reRenderSegmentAudio(0)
            .then(() => {
              setDone(true)
              onReVoiced()
            })
            .catch((err) =>
              setError(err instanceof Error ? err.message : String(err)),
            )
            .finally(() => setBusy(false))
        }}
      >
        {busy ? (
          <>
            <Loader2 className="size-3.5 animate-spin" />
            Re-voicing…
          </>
        ) : (
          <>
            <AudioLines className="size-3.5" />
            Re-voice video
          </>
        )}
      </Button>
    </div>
  )
}

function VoiceDialogBody({
  data,
  apply,
  runActive,
}: {
  data: VoiceState
  apply: (data: VoiceState) => void
  runActive: boolean
}) {
  if (!data.pocket_installed) {
    return (
      <div className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-status-warn">
        <TriangleAlert className="mt-0.5 size-4 shrink-0" />
        <span>
          The voice engine isn't installed. Run{' '}
          <code className="rounded bg-background px-1 font-mono text-xs">
            pip install "pocket-tts" soundfile
          </code>{' '}
          and restart <code className="font-mono text-xs">instantdemo serve</code>.
        </span>
      </div>
    )
  }
  return (
    <Tabs defaultValue="voice">
      <TabsList className="w-full">
        <TabsTrigger value="voice" className="flex-1">
          Voice
        </TabsTrigger>
        <TabsTrigger value="clone" className="flex-1">
          My voice
        </TabsTrigger>
        <TabsTrigger value="pronunciation" className="flex-1">
          Pronunciation
        </TabsTrigger>
      </TabsList>
      <TabsContent value="voice">
        <StockVoiceTab data={data} apply={apply} runActive={runActive} />
      </TabsContent>
      <TabsContent value="clone">
        <CloneTab data={data} apply={apply} runActive={runActive} />
      </TabsContent>
      <TabsContent value="pronunciation">
        <PronunciationTab data={data} apply={apply} runActive={runActive} />
      </TabsContent>
    </Tabs>
  )
}

/** Play a preview Blob; returns when playback starts. */
function playBlob(blob: Blob) {
  const url = URL.createObjectURL(blob)
  const audio = new Audio(url)
  audio.addEventListener('ended', () => URL.revokeObjectURL(url))
  void audio.play()
}

function PreviewButton({
  label,
  request,
  disabled,
  size = 'xs',
}: {
  label?: string
  request: Parameters<typeof previewVoice>[0]
  disabled?: boolean
  size?: 'xs' | 'sm'
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  return (
    <span className="inline-flex items-center gap-1.5">
      <Button
        size={size}
        variant="outline"
        disabled={disabled || busy}
        onClick={() => {
          setBusy(true)
          setError(null)
          previewVoice(request)
            .then(playBlob)
            .catch((err) =>
              setError(err instanceof Error ? err.message : String(err)),
            )
            .finally(() => setBusy(false))
        }}
      >
        {busy ? (
          <Loader2 className="size-3 animate-spin" />
        ) : (
          <Play className="size-3" />
        )}
        {label}
      </Button>
      {error ? (
        <span className="max-w-48 truncate text-xs text-destructive" title={error}>
          {error}
        </span>
      ) : null}
    </span>
  )
}

function prettyVoice(name: string): string {
  return name
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

function StockVoiceTab({
  data,
  apply,
  runActive,
}: {
  data: VoiceState
  apply: (data: VoiceState) => void
  runActive: boolean
}) {
  const [saving, setSaving] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const current = data.config.voice
  const usingClone = data.ref_exists && data.config.ref_wav

  return (
    <div className="flex flex-col gap-2 pt-2">
      {usingClone ? (
        <p className="text-xs text-muted-foreground">
          Your cloned voice is active — the stock voice below is the
          fallback. Remove the clone in “My voice” to switch back.
        </p>
      ) : null}
      {error ? <p className="text-xs text-destructive">{error}</p> : null}
      <ul className="flex max-h-72 flex-col gap-1 overflow-y-auto pr-1">
        {data.voices.map((voice) => (
          <li
            key={voice}
            className={`flex items-center justify-between rounded-md border px-3 py-1.5 ${
              voice === current
                ? 'border-primary/50 bg-primary/5'
                : 'border-border'
            }`}
          >
            <span className="text-sm">
              {prettyVoice(voice)}
              {voice === current ? (
                <span className="ml-2 text-xs text-muted-foreground">
                  current
                </span>
              ) : null}
            </span>
            <span className="flex items-center gap-1.5">
              <PreviewButton request={{ voice, use_reference: false }} />
              {voice !== current ? (
                <Button
                  size="xs"
                  variant="ghost"
                  disabled={runActive || saving !== null}
                  onClick={() => {
                    setSaving(voice)
                    setError(null)
                    updateVoice({ voice })
                      .then(apply)
                      .catch((err) =>
                        setError(
                          err instanceof Error ? err.message : String(err),
                        ),
                      )
                      .finally(() => setSaving(null))
                  }}
                >
                  {saving === voice ? (
                    <Loader2 className="size-3 animate-spin" />
                  ) : (
                    'Use'
                  )}
                </Button>
              ) : null}
            </span>
          </li>
        ))}
      </ul>
      {runActive ? (
        <p className="text-xs text-muted-foreground">
          A run is in progress — voice changes are locked until it
          finishes.
        </p>
      ) : null}
    </div>
  )
}

function CloneTab({
  data,
  apply,
  runActive,
}: {
  data: VoiceState
  apply: (data: VoiceState) => void
  runActive: boolean
}) {
  const fileRef = useRef<HTMLInputElement | null>(null)
  const [consent, setConsent] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleUpload = (file: File) => {
    setBusy(true)
    setError(null)
    uploadReference(file, consent)
      .then(apply)
      .catch((err) =>
        setError(err instanceof Error ? err.message : String(err)),
      )
      .finally(() => setBusy(false))
  }

  return (
    <div className="flex flex-col gap-3 pt-2">
      <p className="text-sm text-muted-foreground">
        Narrate demos in a voice like yours. Record 10–30 seconds of
        natural speech in a quiet room (a phone voice memo works well),
        then upload it here.
      </p>

      {data.ref_exists ? (
        <div className="flex items-center justify-between rounded-md border border-border bg-secondary/20 p-3">
          <span className="flex items-center gap-2 text-sm">
            <Mic className="size-4 text-primary" />
            Your voice is set up
            {data.config.consent?.at ? (
              <span className="text-xs text-muted-foreground">
                (added {new Date(data.config.consent.at).toLocaleDateString()})
              </span>
            ) : null}
          </span>
          <span className="flex items-center gap-1.5">
            <PreviewButton
              label="My voice"
              request={{ use_reference: true }}
              size="sm"
            />
            <PreviewButton
              label={prettyVoice(data.config.voice)}
              request={{ voice: data.config.voice, use_reference: false }}
              size="sm"
            />
            <Button
              size="sm"
              variant="ghost"
              disabled={runActive || busy}
              onClick={() => {
                setBusy(true)
                deleteReference()
                  .then(apply)
                  .catch((err) =>
                    setError(
                      err instanceof Error ? err.message : String(err),
                    ),
                  )
                  .finally(() => setBusy(false))
              }}
            >
              <Trash2 className="size-3.5" />
              Remove
            </Button>
          </span>
        </div>
      ) : (
        <>
          <label className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
              className="mt-0.5 size-4 cursor-pointer"
            />
            <span>
              I have the right to use this voice for generated narration.
            </span>
          </label>
          <input
            ref={fileRef}
            type="file"
            accept="audio/*"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) handleUpload(file)
              e.target.value = ''
            }}
          />
          <Button
            disabled={!consent || busy || runActive}
            onClick={() => fileRef.current?.click()}
            className="w-fit"
          >
            {busy ? (
              <>
                <Loader2 className="size-4 animate-spin" />
                Checking your recording…
              </>
            ) : (
              <>
                <Upload className="size-4" />
                Upload a recording
              </>
            )}
          </Button>
        </>
      )}

      {error ? (
        <div className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-xs text-status-warn">
          <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
          {error}
        </div>
      ) : null}
    </div>
  )
}

function PronunciationTab({
  data,
  apply,
  runActive,
}: {
  data: VoiceState
  apply: (data: VoiceState) => void
  runActive: boolean
}) {
  const [rows, setRows] = useState<PronunciationRow[]>(
    data.config.pronunciations.length > 0
      ? data.config.pronunciations
      : [{ match: '', say: '' }],
  )
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const setRow = (i: number, patch: Partial<PronunciationRow>) =>
    setRows((prev) =>
      prev.map((row, j) => (j === i ? { ...row, ...patch } : row)),
    )

  const dirty =
    JSON.stringify(rows.filter((r) => r.match.trim() && r.say.trim())) !==
    JSON.stringify(data.config.pronunciations)

  return (
    <div className="flex flex-col gap-3 pt-2">
      <p className="text-sm text-muted-foreground">
        When a word comes out wrong, type it like it sounds and listen.
        The fix applies to the narration audio only — on-screen text
        keeps the real spelling.
      </p>
      <div className="flex flex-col gap-2">
        {rows.map((row, i) => (
          <div key={i} className="flex items-center gap-2">
            <input
              value={row.match}
              onChange={(e) => setRow(i, { match: e.target.value })}
              placeholder="Word (e.g. Evernote)"
              className="w-36 rounded-md border border-input bg-background px-2 py-1.5 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
            <span className="text-xs text-muted-foreground">sounds like</span>
            <input
              value={row.say}
              onChange={(e) => setRow(i, { say: e.target.value })}
              placeholder="Ever note"
              className="min-w-0 flex-1 rounded-md border border-input bg-background px-2 py-1.5 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
            <PreviewButton
              request={{
                text: `Here's how ${row.match || 'it'} sounds in a sentence.`,
                pronunciations: [row],
              }}
              disabled={!row.match.trim() || !row.say.trim()}
            />
            <button
              type="button"
              aria-label="Remove row"
              className="rounded p-1 text-muted-foreground hover:bg-secondary hover:text-foreground"
              onClick={() =>
                setRows((prev) =>
                  prev.length > 1 ? prev.filter((_, j) => j !== i) : prev,
                )
              }
            >
              <Trash2 className="size-3.5" />
            </button>
          </div>
        ))}
      </div>
      <div className="flex items-center justify-between">
        <Button
          size="sm"
          variant="ghost"
          onClick={() => setRows((prev) => [...prev, { match: '', say: '' }])}
        >
          <Plus className="size-3.5" />
          Add word
        </Button>
        <Button
          size="sm"
          disabled={!dirty || saving || runActive}
          onClick={() => {
            setSaving(true)
            setError(null)
            updateVoice({
              pronunciations: rows.filter(
                (r) => r.match.trim() && r.say.trim(),
              ),
            })
              .then(apply)
              .catch((err) =>
                setError(err instanceof Error ? err.message : String(err)),
              )
              .finally(() => setSaving(false))
          }}
        >
          {saving ? (
            <>
              <Loader2 className="size-3.5 animate-spin" />
              Saving…
            </>
          ) : (
            'Save'
          )}
        </Button>
      </div>
      {error ? <p className="text-xs text-destructive">{error}</p> : null}
    </div>
  )
}
