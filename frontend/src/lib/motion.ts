// MOTION BUDGET (DESIGN.md principle 15): a motion ships only if it
// explains where something came from or where it went. Decorative
// animation is banned. Current sanctioned inventory:
//   1. stage-face transitions (AnimatePresence fade+rise — explains
//      "the same object changed state")
//   2. the exploration-frames container persisting into the
//      storyboard (layoutId="stage-frames")
//   3. lights-down on playback (CSS class, index.css — chrome
//      recedes so the film is alone)
//   4. .meter-pulse progress bars (progress indicator, exempt)
// That's the whole list. Additions require a reason in this comment.
//
// PLANNED, NOT YET SHIPPED: the scene-cards → chapter-strip
// layoutId morph (storyboard becomes the player's timeline). It
// needs the SceneFrame/ChapterStrip restructure of the film face —
// the highest-regression editing surface — so it lands as its own
// follow-up rather than inside the one-object pass.

export const EASE = [0.32, 0.72, 0, 1] as const
export const DUR = 0.25

export const SPRING = {
  type: 'spring' as const,
  stiffness: 320,
  damping: 32,
}

/** Standard stage-face entrance/exit. */
export const FACE_VARIANTS = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -8 },
}

export const FACE_TRANSITION = { duration: DUR, ease: EASE }
