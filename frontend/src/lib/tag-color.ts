/**
 * Deterministic tag -> color mapping.
 *
 * This is a shared DOMAIN TRUTH. Subsection track-tag colors are assigned by
 * hashing the tag string into a fixed 10-hue palette so a given tag always
 * renders in the same hue across every view. Import `colorForTag` everywhere;
 * never re-derive the hash and never reorder `TAG_PALETTE` (IDs and colors must
 * stay stable). The same hues live as the `--tag-1..10` CSS variables in
 * globals.css; this module is their canonical source in TypeScript.
 *
 * Do not "improve" the algorithm.
 */

/**
 * djb2-style string hash. The `| 0` coerces the accumulator back to a 32-bit
 * signed integer on every step (matching the reference implementation's
 * overflow behavior); `Math.abs` folds the sign so the result indexes a palette.
 */
export function hashString(str: string): number {
  let hash = 0
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) - hash + str.charCodeAt(i)) | 0
  }
  return Math.abs(hash)
}

/**
 * The ten muted track-tag hues, in fixed order. Do not reorder: the index a
 * tag hashes to is part of the stable contract.
 */
export const TAG_PALETTE = [
  '#B06A43',
  '#B8862F',
  '#7E8A45',
  '#5E8C5A',
  '#3E8C82',
  '#4F7CA6',
  '#6A6DB0',
  '#8A5A96',
  '#B05A72',
  '#8A7F70',
] as const

export type TagColor = (typeof TAG_PALETTE)[number]

/** The deterministic hue for a subsection track tag. */
export const colorForTag = (tag: string): TagColor =>
  TAG_PALETTE[hashString(tag) % TAG_PALETTE.length]
