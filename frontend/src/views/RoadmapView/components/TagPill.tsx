import { tagPillStyle } from '../tag-pill-style'

interface TagPillProps {
  tag: string
}

/**
 * A subsection track-tag pill (section 09 §3.5 / §7.4): a small, borderless
 * mono pill whose hue is hash-assigned from the shared palette via
 * {@link tagPillStyle} (background = hue ~16% into `card`, text = hue ~72% into
 * `foreground`). The tag text always shows, so color is redundant reinforcement,
 * never the sole signal. Only track tags are colored: subject tags stay neutral.
 */
export function TagPill({ tag }: TagPillProps) {
  return (
    <span
      style={tagPillStyle(tag)}
      className="inline-block rounded-full px-2 py-0.5 font-mono text-[11.5px] leading-none tracking-[0.02em]"
    >
      {tag}
    </span>
  )
}
