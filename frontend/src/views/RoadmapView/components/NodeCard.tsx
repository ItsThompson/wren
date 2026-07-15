import { Check } from 'lucide-react'

import { colorForTag } from '@/lib/tag-color'
import { isSubsectionDone } from '../progress-derive'
import type { ProgressBinding, Subsection } from '../types'
import { ChecklistRow } from './ChecklistRow'

interface NodeCardProps {
  subsection: Subsection
  /**
   * Present on a published roadmap being tracked: makes the checklist
   * interactive and derives the subsection done-state. Absent in draft preview
   * mode, where the checklist is read-only (a draft is not startable).
   */
  progress?: ProgressBinding
}

/**
 * One subsection ("node") in the list view (section 10 "List view" / NodeCard):
 * title, effort, hash-colored track-tag pills, description, resources as real
 * `<a href>` links, and the checklist. When a progress binding is passed the
 * checklist rows are interactive and the subsection shows its derived done-state
 * (olive check + border tint, no bar); without one the checklist is read-only.
 */
export function NodeCard({ subsection, progress }: NodeCardProps) {
  const resourceIds = subsection.resource_order ?? []
  const itemIds = subsection.item_order ?? []
  const resources = subsection.resources ?? {}
  const items = subsection.checklist_items ?? {}
  const tags = subsection.tags ?? []
  const done = progress ? isSubsectionDone(subsection, progress.checkedIds) : false

  return (
    <article
      className={`rounded-lg border bg-card p-5 ${done ? 'border-success/50' : 'border-border'}`}
    >
      <div className="flex items-baseline justify-between gap-3">
        <div className="flex items-baseline gap-2">
          {done ? (
            <Check aria-hidden className="size-4 shrink-0 self-center text-success" />
          ) : null}
          <h3 className="font-serif text-lg font-medium text-foreground">{subsection.title}</h3>
          {done ? (
            <span className="font-mono text-[11px] uppercase tracking-wide text-success">done</span>
          ) : null}
        </div>
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
        <ul className="mt-4 space-y-1 border-t border-border pt-3">
          {itemIds.map((id) => {
            const item = items[id]
            if (!item) return null
            if (progress) {
              return (
                <ChecklistRow
                  key={id}
                  item={item}
                  checked={progress.checkedIds.has(id)}
                  onToggle={(checked) => progress.onToggle(id, checked)}
                />
              )
            }
            return (
              <li key={id} className="flex items-start gap-2 py-1.5 text-sm text-foreground">
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
