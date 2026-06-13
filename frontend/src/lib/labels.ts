// The film register (DESIGN.md principle 5): every user-facing
// string in the DEFAULT window speaks the studio's language. The
// engineering names (analyze/narrate/...) live in lib/phases.ts and
// appear only inside the Inspector.

/** Present-tense sentence shown while a stage runs (header + stage). */
export const STAGE_SENTENCES: Record<number, string> = {
  1: 'Watching your app…',
  2: 'Writing the storyboard…',
  3: 'Tracing every step…',
  4: 'Rehearsing each scene…',
  5: 'Preparing the recording…',
  6: 'Recording your demo…',
}

/** Past-tense fragment for the pause banner ("Paused after …"). */
export const STAGE_DONE: Record<number, string> = {
  1: 'watching your app',
  2: 'writing the storyboard',
  3: 'tracing every step',
  4: 'rehearsing the scenes',
  5: 'preparing the recording',
  6: 'recording',
}

/** Gerund for the failure banner ("Something went wrong while …"). */
export const STAGE_FAILED_WHILE: Record<number, string> = {
  1: 'watching your app',
  2: 'writing the storyboard',
  3: 'tracing the steps',
  4: 'rehearsing the scenes',
  5: 'preparing the recording',
  6: 'recording your demo',
}

export function stageSentence(phase: number | null): string {
  if (phase === null) return 'Working…'
  return STAGE_SENTENCES[phase] ?? 'Working…'
}

/** Two-stage rehearsal sentence (M8): until the first thumbnail
 * lands the agent is composing its script; after that it's walking
 * the app, and the count is real (observed thumbnails, never an
 * estimate). */
export const REHEARSAL_PLANNING = 'Planning the rehearsal…'

export function rehearsalWalking(count: number): string {
  return `Walking your app — ${count} scene${count === 1 ? '' : 's'} verified`
}

/** During a scoped revision, the rehearsal silently replays the
 * chapters before the one being revised (M8) — this fills that
 * stretch with an honest step count. */
export function rehearsalSetupSentence(current: number, total: number): string {
  return `Walking back through your film — step ${current} of ${total}`
}
