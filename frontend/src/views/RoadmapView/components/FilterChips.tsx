import { tagPillStyle } from '../tag-pill-style'

interface FilterChipsProps {
  /** The distinct track tags to offer as filters (first-appearance order). */
  tags: string[]
  /** The single active filter tag, or null when nothing is filtered. */
  activeTag: string | null
  /** Toggle a tag's filter (selecting the active tag again clears it). */
  onToggle: (tag: string) => void
}

/**
 * The track-tag filter chips above the sections (section 10 "List view",
 * section 09 §7.4). Each chip reuses the track-tag pill look ({@link tagPillStyle});
 * the active chip switches to the LOUD accent tint + terracotta text (§9 accent
 * placement: an active filter is a loud surface). Selecting the active chip
 * again clears the filter and restores every subsection. Nothing renders when a
 * roadmap has no track tags.
 */
export function FilterChips({ tags, activeTag, onToggle }: FilterChipsProps) {
  if (tags.length === 0) return null

  return (
    <div className="mt-6 flex flex-wrap items-center gap-2" role="group" aria-label="Filter by tag">
      {tags.map((tag) => {
        const active = tag === activeTag
        return (
          <button
            key={tag}
            type="button"
            aria-pressed={active}
            onClick={() => onToggle(tag)}
            style={active ? undefined : tagPillStyle(tag)}
            className={`rounded-full px-2.5 py-0.5 font-mono text-[11.5px] tracking-[0.02em] transition-colors ${
              active ? 'bg-accent font-medium text-accent-foreground' : 'hover:opacity-80'
            }`}
          >
            {tag}
          </button>
        )
      })}
    </div>
  )
}
