import { colorForTag } from '@/lib/tag-color'
import type { Subsection } from '../types'

interface NodeCardProps {
  subsection: Subsection
}

/**
 * One subsection ("node") in the draft preview (section 10 "List view" /
 * NodeCard): title, effort, hash-colored track-tag pills, description, resources
 * as real `<a href>` links, and the checklist rendered read-only. Preview mode
 * has no interactive checkboxes: a draft is not startable, so no progress
 * persists (section 10 "Preview mode").
 */
export function NodeCard({ subsection }: NodeCardProps) {
  const resourceIds = subsection.resource_order ?? []
  const itemIds = subsection.item_order ?? []
  const resources = subsection.resources ?? {}
  const items = subsection.checklist_items ?? {}
  const tags = subsection.tags ?? []

  return (
    <article className="rounded-lg border border-border bg-card p-5">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="font-serif text-lg font-medium text-foreground">{subsection.title}</h3>
        {subsection.effort_estimate ? (
          <span className="font-mono text-xs text-muted-foreground">
            {subsection.effort_estimate}
          </span>
        ) : null}
      </div>

      {tags.length > 0 ? (
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {tags.map((tag) => (
            <li
              key={tag}
              className="rounded-full border px-2 py-0.5 text-xs font-medium"
              style={{ color: colorForTag(tag), borderColor: colorForTag(tag) }}
            >
              {tag}
            </li>
          ))}
        </ul>
      ) : null}

      {subsection.description ? (
        <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
          {subsection.description}
        </p>
      ) : null}

      {resourceIds.length > 0 ? (
        <ul className="mt-3 space-y-1">
          {resourceIds.map((id) => {
            const resource = resources[id]
            if (!resource) return null
            return (
              <li key={id} className="text-sm">
                <a
                  href={resource.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-primary underline-offset-4 hover:underline"
                >
                  {resource.title}
                </a>
                <span className="ml-2 font-mono text-xs text-muted-foreground">
                  {resource.type}
                </span>
              </li>
            )
          })}
        </ul>
      ) : null}

      {itemIds.length > 0 ? (
        <ul className="mt-4 space-y-1.5 border-t border-border pt-3">
          {itemIds.map((id) => {
            const item = items[id]
            if (!item) return null
            return (
              <li key={id} className="flex items-start gap-2 text-sm text-foreground">
                <span aria-hidden className="mt-0.5 text-muted-foreground">
                  ☐
                </span>
                {item.text}
              </li>
            )
          })}
        </ul>
      ) : null}
    </article>
  )
}
