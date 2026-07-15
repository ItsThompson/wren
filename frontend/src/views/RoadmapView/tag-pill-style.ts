import type { CSSProperties } from 'react'

import { colorForTag } from '@/lib/tag-color'

/**
 * The section-09 (§3.5) track-tag pill style, computed from the shared hash
 * palette: background = the tag's hue mixed ~16% into `card`, text = the hue
 * mixed ~72% into `foreground`. The hue itself comes from the canonical
 * `colorForTag` util (never re-derived here), so a given tag always renders in
 * the same hue across every view.
 *
 * The raw hue is also exposed as the `--tag-hue` custom property. It is the
 * stable, inspectable signal of which palette hue a tag resolved to (the
 * color-mix expressions above only reference it indirectly), which keeps the
 * hash → color contract assertable without depending on how a given engine
 * resolves `color-mix`.
 */
export function tagPillStyle(tag: string): CSSProperties {
  const hue = colorForTag(tag)
  return {
    '--tag-hue': hue,
    backgroundColor: `color-mix(in oklab, ${hue} 16%, var(--card))`,
    color: `color-mix(in oklab, ${hue} 72%, var(--foreground))`,
  } as CSSProperties
}
