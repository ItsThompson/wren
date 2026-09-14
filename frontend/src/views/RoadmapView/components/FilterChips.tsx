import { tagPillStyle } from '../util/tag-pill-style'

interface FilterChipsProps {
  /** The distinct track tags to offer as filters (first-appearance order). */
  tags: string[]
  /** The independently selected filter tags. */
  selectedTags: ReadonlySet<string>
  /** Toggle one tag without changing the other selections. */
  onToggle: (tag: string) => void
}

/** The independently selectable, naturally wrapping track-tag filter chips. */
export function FilterChips({ tags, selectedTags, onToggle }: FilterChipsProps) {
  if (tags.length === 0) return null

  return (
    <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Filter by tag">
      {tags.map((tag) => {
        const selected = selectedTags.has(tag)
        return (
          <button
            key={tag}
            type="button"
            aria-pressed={selected}
            onClick={() => onToggle(tag)}
            style={tagPillStyle(tag)}
            className={`rounded-full border px-2.5 py-0.5 font-mono text-[11.5px] tracking-[0.02em] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 ${
              selected ? 'border-accent' : 'border-transparent hover:opacity-80'
            }`}
          >
            {tag}
          </button>
        )
      })}
    </div>
  )
}
