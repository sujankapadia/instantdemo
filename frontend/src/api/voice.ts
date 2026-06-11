// Mirrors src/instantdemo/server/routes/voice.py (M3, #59).
// Hand-maintained, like the other api modules.

export interface PronunciationRow {
  match: string
  say: string
}

export interface VoiceConfig {
  provider: string
  voice: string
  ref_wav: string | null
  pronunciations: PronunciationRow[]
  consent: { given: boolean; at: string } | null
}

export interface VoiceState {
  config: VoiceConfig
  persisted: boolean
  ref_exists: boolean
  pocket_installed: boolean
  voices: string[]
}

async function parseError(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: string }
    if (body.detail) return body.detail
  } catch {
    // non-JSON body
  }
  return `HTTP ${res.status}`
}

export async function fetchVoice(): Promise<VoiceState> {
  const res = await fetch('/api/project/voice')
  if (!res.ok) throw new Error(await parseError(res))
  return (await res.json()) as VoiceState
}

export async function updateVoice(update: {
  voice?: string
  pronunciations?: PronunciationRow[]
}): Promise<VoiceState> {
  const res = await fetch('/api/project/voice', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(update),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return (await res.json()) as VoiceState
}

export async function uploadReference(
  file: File,
  consent: boolean,
): Promise<VoiceState> {
  const form = new FormData()
  form.append('file', file)
  form.append('consent', consent ? 'true' : 'false')
  const res = await fetch('/api/project/voice/reference', {
    method: 'POST',
    body: form,
  })
  if (!res.ok) throw new Error(await parseError(res))
  return (await res.json()) as VoiceState
}

export async function deleteReference(): Promise<VoiceState> {
  const res = await fetch('/api/project/voice/reference', {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error(await parseError(res))
  return (await res.json()) as VoiceState
}

export async function previewVoice(opts: {
  text?: string
  voice?: string
  use_reference?: boolean
  pronunciations?: PronunciationRow[]
}): Promise<Blob> {
  const res = await fetch('/api/project/voice/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(opts),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return await res.blob()
}
