// Mirrors src/instantdemo/server/routes/storyboard.py (M2) and the
// storyboard.json schema from src/instantdemo/storyboard.py (M0).
// Hand-maintained, like the other api modules.

export type SceneStatus =
  | 'planned'
  | 'hypothesized'
  | 'verified'
  | 'warn'
  | 'failed'

export interface SceneRevision {
  type: string
  from: string
  to: string
  reason: string
  iteration: number
  /** 0 = user edit at the storyboard gate; 4 = Phase 4 rehearsal. */
  phase: number
}

export interface SceneVerification {
  status?: string
  reason?: string
  suggestion?: string | null
  /** One plain sentence for the maker (M5b): what the warning means
   * for their film. Shown inline at the gate; `reason` is hover. */
  note_for_user?: string | null
}

export interface StoryboardScene {
  id: string
  index: number
  title: string
  narration: string
  action: string
  target_hint?: string
  status: SceneStatus
  selector?: string[]
  wait_for?: string[]
  pause_after_ms?: number | null
  notes?: string
  rehearsal_screenshot?: string | null
  verification?: SceneVerification | null
  revisions?: SceneRevision[]
  [key: string]: unknown
}

export interface StoryboardDoc {
  version: number
  title: string
  url: string
  summary: string
  updated_at: string
  scenes: StoryboardScene[]
  [key: string]: unknown
}

export interface StoryboardResponse {
  exists: boolean
  storyboard: StoryboardDoc | null
}

export async function fetchStoryboard(): Promise<StoryboardResponse> {
  const res = await fetch('/api/project/storyboard')
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return (await res.json()) as StoryboardResponse
}

export async function patchSceneNarration(
  sceneId: string,
  narration: string,
): Promise<StoryboardScene> {
  const res = await fetch(`/api/project/storyboard/scenes/${sceneId}`, {
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
      // non-JSON body; keep the HTTP code
    }
    throw new Error(msg)
  }
  return (await res.json()) as StoryboardScene
}
