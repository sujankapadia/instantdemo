// Mirrors Pydantic models in src/instantdemo/server/routes/project.py.
// Hand-maintained for now; revisit type generation if drift becomes a problem.

export type PhaseStatus =
  | 'pending'
  | 'in_progress'
  | 'completed'
  | 'error'

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
