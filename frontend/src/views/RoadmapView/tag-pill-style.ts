import type { CSSProperties } from 'react'

import { colorForTag } from '@/lib/tag-color'

/**
 * The section-09 (§3.5) track-tag pill style, computed from the shared hash
 * palette: background = the tag's hue mixed ~16% into `card`, text = the hue
 * mixed ~72% into `foreground`. The hue itself comes from the canonical
 * `colorForTag` util (never re-derived here), so a given tag always renders in
 * the same hue across every view.
 *
 * The hue is set once as the `--tag-hue` custom property and the color-mix
 * expressions read `var(--tag-hue)`, so the exposed variable is load-bearing
 * (the single source of the pill's color) rather than a duplicate copy. It is
 * also the stable, inspectable signal of which palette hue a tag resolved to,
 * which keeps the hash → color contract assertable without depending on how a
 * given engine resolves `color-mix`.
 */
export function tagPillStyle(tag: string): CSSProperties {
  return {
    '--tag-hue': colorForTag(tag),
    backgroundColor: 'color-mix(in oklab, var(--tag-hue) 16%, var(--card))',
    color: 'color-mix(in oklab, var(--tag-hue) 72%, var(--foreground))',
  } as CSSProperties
}
