// Mirrors src/instantdemo/server/routes/takes.py (M4).

export interface Take {
  n: number
  label: string
  created_at: string | null
  video_exists: boolean
  /** This take's video IS the current film — not a previous version. */
  is_current: boolean
}

export async function fetchTakes(): Promise<Take[]> {
  const res = await fetch('/api/project/takes')
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const body = (await res.json()) as { takes: Take[] }
  return body.takes
}

export function takeVideoUrl(n: number): string {
  return `/api/project/takes/${n}/video`
}

export async function restoreTake(n: number): Promise<void> {
  const res = await fetch(`/api/project/takes/${n}/restore`, {
    method: 'POST',
  })
  if (!res.ok) {
    let msg = `HTTP ${res.status}`
    try {
      const body = (await res.json()) as { detail?: string }
      if (body.detail) msg = body.detail
    } catch {
      // non-JSON body
    }
    throw new Error(msg)
  }
}
