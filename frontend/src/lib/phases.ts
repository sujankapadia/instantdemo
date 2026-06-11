// INSPECTOR-ONLY phase names (DESIGN.md principle 5): the canonical
// engineering identifiers, matching artifact filenames (phase2.md ↔
// narrate), prompts, and the CLI. The default window never shows
// these — it speaks the film register from lib/labels.ts.

export const PHASE_NAMES: Record<number, string> = {
  1: 'analyze',
  2: 'narrate',
  3: 'gather',
  4: 'explore',
  5: 'script',
  6: 'render',
}

export const PHASE_NAMES_ORDERED = [
  PHASE_NAMES[1],
  PHASE_NAMES[2],
  PHASE_NAMES[3],
  PHASE_NAMES[4],
  PHASE_NAMES[5],
  PHASE_NAMES[6],
] as const

export function phaseName(num: number): string {
  return PHASE_NAMES[num] ?? `phase ${num}`
}
