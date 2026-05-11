// User-facing names for the 5-phase pipeline. The backend identifiers
// stay lowercase (analyze / narrate / gather / script / validate)
// since they're embedded in artifact filenames, agent prompts, and the
// CLI surface. These display names are GUI-only.

export const PHASE_NAMES: Record<number, string> = {
  1: 'Understand',
  2: 'Plan',
  3: 'Inspect',
  4: 'Build',
  5: 'Verify',
}

export const PHASE_NAMES_ORDERED = [
  PHASE_NAMES[1],
  PHASE_NAMES[2],
  PHASE_NAMES[3],
  PHASE_NAMES[4],
  PHASE_NAMES[5],
] as const

export function phaseName(num: number): string {
  return PHASE_NAMES[num] ?? `Phase ${num}`
}
