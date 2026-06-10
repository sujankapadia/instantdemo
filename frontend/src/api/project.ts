// Mirrors Pydantic models in src/instantdemo/server/routes/project.py.
// Hand-maintained for now; revisit type generation if drift becomes a problem.

export type PhaseStatus =
  | 'pending'
  | 'in_progress'
  | 'completed'
  | 'error'
  | 'canceled'

export type ExploreSegmentStatus =
  | 'PASS'
  | 'FAIL_SELECTOR'
  | 'FAIL_NARRATIVE'
  | 'WARN'

export interface ExploreSegmentFinding {
  index: number
  status: ExploreSegmentStatus
  reason?: string
  suggestion?: string
  selector_swapped?: boolean
  from?: string
  to?: string
}

export interface ExploreFindings {
  summary?: {
    total?: number
    pass?: number
    fail_selector?: number
    fail_narrative?: number
    warn?: number
    overall?: 'OK' | 'BLOCKED'
  }
  segments?: ExploreSegmentFinding[]
}

// Phase 1 (explore-first, M1): one entry per screen the agent visited.
export interface ScreenInfo {
  name: string
  route?: string | null
  screenshot?: string | null
  notes?: string | null
}

export interface PhaseState {
  status?: PhaseStatus
  started_at?: string
  completed_at?: string
  cost_usd?: number
  duration_ms?: number
  num_turns?: number
  // Phase 4 (Explore) only. Structured findings from the agent's JSON
  // block, written to state.json by the runner. See issue #48.
  explore_findings?: ExploreFindings
  explore_overall?: 'OK' | 'BLOCKED'
  // Phase 1 (M1) only: the agent's proposed demo intent + visited
  // screens + warnings — feeds the intent-confirmation card.
  intent_proposal?: import('./runs').Intent | null
  screens?: ScreenInfo[] | null
  warnings?: string[] | null
}

export interface ProjectState {
  exists: boolean
  name: string
  project_dir: string
  url?: string | null
  describe?: string | null
  // Persisted source path for the Regenerate flow to prefill.
  source?: string | null
  // Current intent (loaded from intent.json or synthesized from describe).
  // Frontend uses this to prefill the Regenerate form.
  intent?: import('./runs').Intent | null
  session_id?: string | null
  created_at?: string | null
  phases: Record<string, PhaseState>
  current_run_id?: string | null
  // Two-run intent confirmation (M1): the confirm card shows when a
  // proposal exists and this is false. Derived server-side so a page
  // reload mid-flow re-shows the card.
  intent_confirmed?: boolean
  // Storyboard gate (M2): false after the [2,3,4] rehearsal leg;
  // true once a run including phase 5/6 starts. The approve bar
  // shows when a rehearsed storyboard exists and this is false.
  storyboard_approved?: boolean
}

// --- M1: exploration screenshots + pre-flight ---

export async function fetchExplorationShots(): Promise<{ files: string[] }> {
  const res = await fetch('/api/project/exploration')
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return (await res.json()) as { files: string[] }
}

export interface PreflightResponse {
  ok: boolean
  title?: string | null
  final_url?: string | null
  screenshot: boolean
  error?: string | null
}

export async function runPreflight(
  url: string,
  signal?: AbortSignal,
): Promise<PreflightResponse> {
  const res = await fetch('/api/preflight', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
    signal,
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return (await res.json()) as PreflightResponse
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
