// Mirrors Pydantic models in src/instantdemo/server/routes/segments.py.

export interface SegmentResponse {
  index: number
  action: string
  narration: string
}

export interface ReRenderResult {
  ok: boolean
  duration_ms: number
  new_audio_duration_ms: number
  overflow: boolean
}

export async function patchSegmentNarration(
  index: number,
  narration: string,
): Promise<SegmentResponse> {
  const res = await fetch(`/api/segments/${index}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ narration }),
  })
  if (!res.ok) {
    let msg = `HTTP ${res.status}`
    try {
      const body = (await res.json()) as { detail?: string }
      if (body.detail) msg = body.detail
    } catch {
      // body wasn't JSON; fall through with HTTP code
    }
    throw new Error(msg)
  }
  return (await res.json()) as SegmentResponse
}

export async function reRenderSegmentAudio(
  index: number,
): Promise<ReRenderResult> {
  const res = await fetch(`/api/segments/${index}/re-render-audio`, {
    method: 'POST',
  })
  if (!res.ok) {
    let msg = `HTTP ${res.status}`
    try {
      const body = (await res.json()) as { detail?: string }
      if (body.detail) msg = body.detail
    } catch {
      // body wasn't JSON; fall through with HTTP code
    }
    throw new Error(msg)
  }
  return (await res.json()) as ReRenderResult
}
