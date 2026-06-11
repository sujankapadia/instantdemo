# DESIGN.md — the bar the product is held to

Written 2026-06-10, after the M0–M3 arc shipped and the M4 design
review. This is the standing design philosophy for InstantDemo's
user-facing product. Every milestone's UI work gets measured against
it. (The developer/CLI surface is exempt — it serves a different
person and may show its machinery.)

## What this object is

**A small film studio that makes one film: yours.** The user
commissions; the studio watches their app, proposes a treatment,
storyboards it, rehearses, records, and delivers a cut. Revisions
are notes and takes.

Everything that supports that story belongs. Everything that exposes
the factory — phases, pipelines, classifiers, panes, meters —
is apparatus, and apparatus must recede.

## Principles

1. **The film is the object; everything defers to it.** The center
   of the screen belongs to the demo taking shape. Controls annotate
   the object; they never compete with it.

2. **One object maturing, not rooms in sequence.** The journey —
   exploration filmstrip → proposal → storyboard → rehearsed scenes
   → playable film — is ONE surface continuously transforming. Every
   hard transition between "screens" is a cut, and cuts spend trust.

3. **Welcome the brief; never impose the schema.** The user knows
   their product — audience, tone, what to cover is THEIR expertise,
   and the intake receives it fluently: the app's address plus one
   free-text brief box, written in their words at whatever length
   they have. Discoverability lives in three places, not in labeled
   blanks: a worked-example ghost text that demonstrates every lever
   in use ("This is for prospective customers — not technical.
   Friendly tone. Focus on the export flow; skip settings. Never
   show real customer names."); one muted hint line naming what can
   be mentioned; and the confirm card's structured readback, which
   teaches what a brief CAN say by showing what this one DID say.
   The schema is internal filing the agent derives — extraction
   follows the verbatim-rule (every brief sentence lands somewhere;
   when unsure, addenda verbatim — omission structurally
   impossible) and is always played back for confirmation before
   anything is spent. Follow-up questions are reserved for what the
   user didn't say and the studio discovered it needs after looking
   ("I couldn't get past the login") — evidence-based, in context,
   with the reason attached.

4. **Two audiences, two surfaces.** The maker persona gets the
   default window with zero machinery. The developer's apparatus
   (stage internals, artifacts, logs, costs) lives behind a
   deliberate threshold — an inspector you GO to — not a mode
   toggle in the same room. Modes erode confidence.

5. **Speak film, completely.** Scenes, storyboard, treatment,
   rehearsal, recording, cut, takes, notes. Never: phase, pipeline,
   segment index, classifier, render queue, tier. The internal stage
   names (analyze/narrate/gather/explore/script/render) are
   coordinates for engineers; the user-facing register is a film
   studio's.

6. **State certainties, not estimates.** Before a spend: what will
   change and what won't ("your screens stay exactly as they are —
   only the voice changes"). Never predicted seconds or cents
   (machine-dependent, hosting-dependent — not trustworthy). Actuals
   may be reported after, quietly.

7. **Reversibility so effortless it isn't a feature.** Every
   revision keeps the previous take; comparison is an act of looking
   (flip between cuts), not file management. No warnings where an
   undo would do.

8. **The change is felt, not reported.** After a revision, play the
   changed moment. Confirmation is the object itself, not a receipt.

9. **Honesty about authority.** When a request exceeds what the
   current operation can do, the answer is the same calm voice
   offering the bigger door ("that means reworking the demo — I can
   do that with this folded into your brief"), never a rejection
   sorted into an error section. Nothing silently exceeds its
   authority; nothing silently spends.

10. **Protect the signature moment.** The live exploration filmstrip
    — the user watching the system watch their app — is the moment
    trust transfers. It is the identity of the product and should be
    staged as such: centered, unhurried, concluding naturally in the
    proposal.

11. **Accept only commitments you honor measurably.** Every input
    the product offers is a promise that the input matters. A field
    consumed as a mere prompt-hint with no downstream check is a
    false promise — remove it or close the loop. Precedent: the
    intent `length` field was removed (2026-06-11) because nothing
    measured the rendered duration against it; if a length contract
    returns, it returns WITH its measurement (content-math estimate
    at the gate, actual-vs-target check post-render — output
    duration is content math, not a machine-dependent prediction,
    so principle 6 permits it).

## Craft — how it looks, moves, and feels

The principles above govern structure and voice; these govern the
pixels. Diagnosis (2026-06-11): a developer-tool skin on a
creative-tool soul — competent shadcn defaults, anonymous. The
interface should belong to the same world as what it makes.

12. **The material is a screening room.** Deep warm-neutral dark
    (video and screenshots are the brightest things on screen;
    chrome sits in shadow). ONE signature accent, used like a tally
    light — only on the action that matters per screen (approve,
    record, make-these-changes). Status marks are quiet dot+label,
    not saturated pills; saturation is earned by importance.

13. **Two typographic registers.** Chrome speaks small and neutral;
    THE STUDIO speaks — proposal, gate summary, answers — in a
    distinct, more generous register. When the product talks to the
    user it should look like a voice, not a label that grew.

14. **The stage is sacred.** On play, lights down: surrounding UI
    dims, controls fade, the film is alone. Storyboard cards are
    FRAMES — true 16:9 thumbnails, narration as caption, filmstrip
    visual language — not admin cards with images attached.

15. **Motion explains causality; nothing else moves.** Shared-
    element continuity is the teaching tool: exploration frames
    BECOME storyboard cards; cards BECOME the player timeline on
    approve. One easing family, ~250ms, springs. Hard budget: a
    motion that doesn't explain where something came from doesn't
    ship. (React conditionals popping in/out are not transitions.)

16. **Show the medium.** A voice product's interface visibly
    contains audio: previews draw a small waveform as they play;
    re-voicing pulses like a meter, not a generic spinner.

17. **Sweat the unglamorous states.** Skeletons match real layout;
    the empty state is the most-designed screen in the app (it's
    the front door — the URL field is the hero); blur-up thumbnails;
    consistent focus rings; hover lift; errors keep their layout.

## The consolidation backlog (the "one object" pass)

Concrete gaps between today's product and the principles above,
ordered by cost. Items 1–3 are cheap and can precede the next
feature milestone; items 4–5 are the core project and should land
BEFORE M4-rescoped/M5 build their UI (takes toggle, style box,
chapters all belong on the unified surface). Structure (4) and skin
(5) are ONE milestone — both rebuild the same surfaces; doing them
separately means restyling twice.

1. ✅ 2026-06-11 **Vocabulary commit (S).** User-facing copy sweeps to the film
   register. Stage labels (Understand/Plan/Inspect/Explore/Build/
   Render) become studio language in the default window; "Segment N"
   becomes "Scene N" post-render to match the storyboard.
2. ✅ 2026-06-11 **Brief-box start (M).** The New Project modal collapses to URL
   + pre-flight ("I see it") + ONE free-text brief box that welcomes
   everything the user already knows (audience, tone, coverage, in
   their own words; a paragraph or a single line — both first-class).
   The agent derives the structured intent from the brief; the
   proposal plays it back for confirmation/refinement (M1's
   yes-and). Source/docs become evidence-based offers when
   exploration finds it needs them. Pause-between-phases moves to
   the inspector.
3. ✅ 2026-06-11 **Kill the mode toggle (M).** Details mode (phase rail, artifact
   editor, log drawer, cost meter) moves to a distinct inspector
   surface; the default window has no toggle and no running invoice.
   Costs surface at decision moments and in the inspector.
4. ✅ 2026-06-11 **One maturing surface (L).** Merge filmstrip → proposal →
   storyboard → player into the single center-stage object:
   exploration fills empty frames with screenshots; the proposal
   annotates; rehearsal verifies scene by scene (chips, thumbnails);
   approval turns the same cards into the playable film. The video
   player is the storyboard, finished. Absorbs the
   signature-moment staging (10).
5. ✅ 2026-06-11 (scene→chapter morph deferred — see lib/motion.ts budget note) **The craft layer (L, concurrent with 4).** Design tokens
   (screening-room palette, type scale with the two registers,
   spacing); motion system (one easing family + the continuity
   transitions of principle 15); frame-styled scene cards;
   lights-down stage treatment; waveform audio affordances; the
   unglamorous-states audit (17).

## Already aligned (don't regress)

Pre-flight before questions; the live filmstrip; confirmation-not-
configuration (intent card, storyboard gate); suggestion-first
failure notices; plain-language validation errors ("the recording is
silent — check your microphone"); the no-predictions rule; takes
kept on every revision; the persona vocabulary rule in prompts
(enforced by smoke-test grep). These were won deliberately across
M1–M4; they are the floor, not the aspiration.
