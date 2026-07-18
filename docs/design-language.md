# Wren design language

The durable rules behind Wren's look and feel: how to make a frontend or design
change that stays *warm, minimal, and inviting* rather than drifting into a
generic dashboard. Read this before touching UI; it is the "why" and the
"when," not the "what."

**Token values are not in this document.** Every color, radius, and font value
lives in code as the single source of truth; this guide names *roles* and
*rules* and points at the code for the numbers. Naming a hue (terracotta, olive)
is fine here; hex/oklch values are not.

| Concern | Canonical source (do not duplicate) |
|---------|-------------------------------------|
| Color / radius / font-family tokens | `frontend/src/globals.css` |
| Font faces (self-hosted, Latin subset) | `frontend/src/fonts.css` |
| Tag hue palette + hash function | `frontend/src/lib/tag-color/tag-color.ts` |
| Display-type + reading-width utilities | `frontend/src/globals.css` (`display-xl/l/m`, `reading-width`) |
| Component implementations | `frontend/src/components/**`, `frontend/src/views/**` |

Target stack: React + Tailwind v4 + shadcn/ui. shadcn components inherit these
tokens automatically, so a new component should look right with no per-component
color work. No dark mode this round.

---

## 1. Principles

Wren should feel like a well-made paper notebook, not a control panel.

1. **Warm over neutral.** Never pure black on pure white. The ground is
   bone/cream, the ink is warm espresso, and every gray leans warm (taupe/stone),
   never blue.
2. **Minimal, but not cold.** Restraint in the *quantity* of elements and chrome;
   generosity in whitespace, type size, and warmth. When in doubt, remove.
3. **Accent-forward where it counts, calm where you read.** The terracotta accent
   is loud on high-impact surfaces and recedes to punctuation in dense reading
   areas. This tension is governed by the accent placement map (§3).
4. **Editorial, human typography.** A humanist grotesque carries the interface; a
   warm serif appears only for the big human moments.
5. **Content is the interface.** Roadmaps are the product. Chrome (nav, borders,
   shadows) stays quiet so the learner's content and progress carry the color and
   weight.

New work is judged against these five. An addition (a new semantic hue, a new
component variant) has to justify itself here first; prefer removing over adding.

---

## 2. Brand and voice

- **Name/domain:** Wren, `usewren.com`. The wren is a small brown bird: earthy,
  warm, quick, unassuming. That drives the palette (clay, sand, espresso, olive)
  and a modest, grounded identity.
- **Wordmark:** lowercase `wren` set in the display serif with tight tracking.
  This is the one place the brand signs its name in serif; everything else is
  grotesque. No bird glyph.
- **Voice in UI copy:** plain, encouraging, second person. "Pick up where you
  left off," not "Resume session."

---

## 3. Color

The palette has a deliberate shape: **one** warm accent does the heavy lifting, a
warm-neutral ground and ink carry everything else, **three** semantic hues cover
done/destructive/warning, and a separate muted palette handles tags. There is no
cool "info blue": informational emphasis uses ink, neutral, or the accent.

### 3.1 The accent placement map (the governing rule)

This single table is what keeps "accent-forward" from fighting "minimal." When
adding anything terracotta, place it in the right column first.

| Register | Where terracotta appears | Examples |
|----------|--------------------------|----------|
| **Loud** (fills, large type, blocks) | High-impact, low-density surfaces | Landing hero, primary CTAs, roadmap + section progress fills, the "next" node highlight, active filter chip, empty-state action, focus rings |
| **Calm** (cream + ink; terracotta only as link/icon/1px accent) | Dense reading areas | Checklist rows, node card bodies, node detail, section/subsection text, top bar, forms, badges, metadata |
| **Never** | — | Terracotta as a card background behind reading content; terracotta on subject tags; more than one serif display moment per dense view |

### 3.2 Semantic hues

Three hues, each with a fixed meaning. Never repurpose them, and never rely on
the hue alone to carry the meaning (see §8).

| Hue | Meaning | Used for |
|-----|---------|----------|
| Olive / sage | done / success | Completed items and subsections, checkmarks, "done" tree nodes |
| Brick red | destructive | Delete, archive, unpublish. Deeper and cooler than the accent so it never reads as "accent" |
| Ochre / amber | warning | Stale-revision "re-read," validation hard-blocks, publish gates |

Brick and terracotta are close in hue; never place them adjacent for *different*
meanings without a shape or label difference to separate them.

### 3.3 Tags

Tag color is a **domain truth**, not a styling choice. Subsection track tags are
colored deterministically by hashing the tag string into a fixed muted palette,
so a given tag renders in the same hue in every view. The hash and palette are
canonical in `frontend/src/lib/tag-color/tag-color.ts` (mirrored as CSS
variables in `globals.css`). Import that util everywhere; never re-derive the
hash and never reorder the palette.

**Subject tags** (roadmap-level categorization) are the exception: they render as
**neutral** chips, never hued. Coloring them would double the color load and blur
the two concepts. Only subsection track tags get a hue.

### 3.4 Contrast posture

Cream-on-terracotta is only safe for larger, heavier labels, so terracotta fills
carry medium-weight-or-heavier labels only, never long or fine text. Terracotta
used *as text* (links, emphasis) uses the darker link shade defined in
`globals.css`, which clears contrast for body copy. Full contrast rules are in
§8.

---

## 4. Typography

An editorial-warm pairing: the grotesque carries the interface, the serif is a
spice used for human moments. Three faces, each with a job. Faces and weights are
defined in `frontend/src/fonts.css`; the type scale and display utilities live in
`globals.css`.

| Face | Role |
|------|------|
| Display serif (Fraunces) | Hero titles, section intros, empty-state lines, the wordmark, pull-quotes. **Never** body or UI labels. |
| Humanist grotesque (Hanken Grotesk) | The workhorse: all UI, body copy, most headings, buttons, nav. |
| Monospace (JetBrains Mono) | Tags, effort estimates, IDs/slugs, resource-type labels, countdowns, keyboard hints, code. |

Rules:

- **One serif display moment per dense view, maximum.** It is a spice; overuse
  makes it generic. The `display-*` utilities in `globals.css` mark these
  moments.
- **Tabular numerals** (`font-variant-numeric: tabular-nums`) for anything that
  counts or updates in place: progress percentages, countdowns.
- **Body line length ~68ch;** reading views center at a fixed reading width (the
  `reading-width` utility).

---

## 5. Shape, spacing, elevation

- **Radius:** soft and round, never bubbly, never sharp. Cards/panels and
  buttons/inputs use the shared radius scale in `globals.css`; tags and progress
  bars are full pills. No hard bracket corners.
- **Spacing:** generous, on a 4px grid. Whitespace is a feature, not waste.
  Reading views are a centered column; the tree/dashboard may go wider.
- **Elevation: borders first, shadow second.** Cards are a 1px border on a raised
  surface. Reserve a single soft shadow for popovers, menus, and the "next" card;
  no heavy drop shadows anywhere else.
- **Dividers** are 1px borders; between dense list rows use a fainter mix.

---

## 6. Iconography and motion

- **Icons:** lucide, a single consistent stroke, never filled, never emoji. Icon
  color matches the adjacent text (quiet metadata color for quiet contexts, ink
  or accent for active ones).
- **Motion:** minimal and quick. Short ease-out transitions on hover, expand, and
  check; progress bars animate their width. No bounce, no parallax. Always honor
  `prefers-reduced-motion` (the base stylesheet already disables motion when it is
  requested).

---

## 7. Components (intent)

Each maps to a shadcn/ui primitive and inherits the tokens; this section is the
*intent*, not the markup. Implementations live under
`frontend/src/components/**`. Match the nearest existing sibling when adding one.

- **Buttons.** Primary = terracotta fill with a cream label (the accent-forward
  CTA); secondary = quiet neutral fill; ghost = transparent, for low-priority and
  toolbar actions; destructive = brick fill, confirm-gated; link = accent-colored
  text on a real `<a href>` for navigation.
- **Cards.** A raised surface with a 1px border and generous padding. The "next"
  card is the one card that earns the accent-tint border plus the reserved soft
  shadow.
- **Progress.** Full-pill track with a solid terracotta fill (no gradient).
  **Bars exist only at roadmap and section level.** Subsections and items never
  get a bar; their completion is shown by the done-state instead.
- **Checklist row.** The atomic checkable unit. Checked = olive fill with a cream
  check, and the label goes quiet + struck through. Completion lives here.
- **Done-state (subsection).** No bar: an olive check on the title, an olive-tinted
  card border, a small "done" label. Subtle, not a full green fill.
- **Tags / filter chips.** Track tags are hued pills (§3.3); subject tags are
  neutral; the active filter chip takes the accent tint + accent text.
- **Inputs.** Quiet fill, 1px border, a visible accent focus ring (§8), labels in
  the caption size.
- **Empty states.** The one place serif + warmth shine: one serif line, a quiet
  sub-line, one primary action, encouraging copy.
- **Badges.** Status (draft/published/archived) and visibility (private/public)
  read by shape and label, not color alone.

---

## 8. Accessibility

- **Never encode meaning by color alone.** Done = olive **and** a check **and**
  strikethrough; tree node state = color **and** icon; validation = ochre **and**
  the message text. Tags always show their text label, so hue is reinforcement,
  never the sole signal.
- **Contrast.** Body ink on paper is far past AA; the quiet secondary text clears
  AA for body. Terracotta fills carry only larger, heavier labels; terracotta as
  text uses the darker link shade (§3.4).
- **Focus.** Always-visible accent focus ring with an offset; never remove
  outlines. The base stylesheet supplies a default ring for anything a shadcn
  component does not.
- **Motion.** Honor `prefers-reduced-motion` (§6).

---

## 9. Extending this language

This language is deliberately small; that is the point. Before adding a token, a
hue, or a component variant:

1. Justify it against the principles in §1, and prefer removing over adding.
2. Add token *values* to `frontend/src/globals.css` only (oklch is canonical
   there); document the new *rule* here, without restating the value.
3. The tag palette and hash are a frozen contract: extend deliberately and never
   reorder, or existing roadmaps change color.

When dark mode is eventually added, it redefines the same token variables under a
dark scope (a warm charcoal ground, cream ink, the accent held constant, tag hues
lifted in lightness). Do not introduce dark-mode tokens before then.
