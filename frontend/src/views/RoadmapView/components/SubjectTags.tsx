interface SubjectTagsProps {
  tags: string[]
}

/**
 * The roadmap-level subject tags (section 04/09): neutral secondary chips, never
 * hash-colored (only subsection track tags get color). Shared by the draft
 * preview and the published list-view headers.
 */
export function SubjectTags({ tags }: SubjectTagsProps) {
  if (tags.length === 0) return null
  return (
    <ul className="mt-4 flex flex-wrap gap-2">
      {tags.map((tag) => (
        <li
          key={tag}
          className="rounded-md bg-secondary px-2 py-0.5 text-xs text-secondary-foreground"
        >
          {tag}
        </li>
      ))}
    </ul>
  )
}
