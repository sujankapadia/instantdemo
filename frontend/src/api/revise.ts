// Mirrors src/instantdemo/server/routes/revise.py (M4).

export interface ReviseResponse {
  kind: 'rewrite' | 'pace' | 'voice' | 'structural' | 'unclear'
  explanation: string
  suggestion: string | null
  rewrites_applied: number
  pace_factor: number | null
  needs_rerecord: boolean
  first_changed_index: number | null
  take_n: number | null
  storyboard_synced: boolean
  cost_usd: number
}

export async function reviseDemo(
  instruction: string,
): Promise<ReviseResponse> {
  const res = await fetch('/api/project/revise', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ instruction }),
  })
  if (!res.ok) {
    let msg = `HTTP ${res.status}`
    try {
      const body = (await res.json()) as { detail?: string }
      if (body.detail) msg = body.detail
    } catch {
      // non-JSON
    }
    throw new Error(msg)
  }
  return (await res.json()) as ReviseResponse
}
