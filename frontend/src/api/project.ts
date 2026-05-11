// Mirrors Pydantic models in src/instantdemo/server/routes/project.py.
// Hand-maintained for now; revisit type generation if drift becomes a problem.

export type PhaseStatus =
  | 'pending'
  | 'in_progress'
  | 'completed'
  | 'error'
  | 'canceled'

export interface PhaseState {
  status?: PhaseStatus
  started_at?: string
  completed_at?: string
  cost_usd?: number
  duration_ms?: number
  num_turns?: number
}

export interface ProjectState {
  exists: boolean
  name: string
  project_dir: string
  url?: string | null
  describe?: string | null
  session_id?: string | null
  created_at?: string | null
  phases: Record<string, PhaseState>
  current_run_id?: string | null
}

export async function fetchProject(): Promise<ProjectState> {
  const res = await fetch('/api/project')
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return (await res.json()) as ProjectState
}

export type PhaseNumber = 1 | 2 | 3 | 4 | 5
export type ArtifactFormat = 'markdown' | 'json'

export interface ArtifactResponse {
  phase: PhaseNumber
  format: ArtifactFormat
  exists: boolean
  content: string | null
}

export async function fetchArtifact(phase: PhaseNumber): Promise<ArtifactResponse> {
  const res = await fetch(`/api/project/artifacts/${phase}`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return (await res.json()) as ArtifactResponse
}

// Mirrors Pydantic Segment model in routes/project.py. Action-specific
// fields (selector, url, value, pixels, wait_for, frame, key, expression)
// pass through via [key: string]: unknown so we can read them when the
// underlying script has them, without re-typing them all here.
export interface Segment {
  index: number
  action: string
  narration: string
  pause_after_ms: number | null
  start_s: number | null
  end_s: number | null
  audio_duration_s: number | null
  recorded_clean_duration_s: number | null
  audio_overflows: boolean | null
  [key: string]: unknown
}

export interface SegmentsResponse {
  exists: boolean
  has_timing: boolean
  total_duration_s: number | null
  segments: Segment[]
}

export async function fetchSegments(): Promise<SegmentsResponse> {
  const res = await fetch('/api/project/segments')
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return (await res.json()) as SegmentsResponse
}
