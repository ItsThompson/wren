import { type FormEvent, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import type { MetadataDraft, MetadataEditState, Roadmap } from '../types'

interface MetadataEditorProps {
  roadmap: Roadmap
  state: MetadataEditState
  onSave: (draft: MetadataDraft) => void | Promise<unknown>
  onCancel: () => void
}

/** Parse the comma-separated subject-tags input into a trimmed, de-duped list. */
function parseTags(raw: string): string[] {
  const seen = new Set<string>()
  const tags: string[] = []
  for (const part of raw.split(',')) {
    const tag = part.trim()
    if (tag && !seen.has(tag)) {
      seen.add(tag)
      tags.push(tag)
    }
  }
  return tags
}

/**
 * The presentation-only metadata editor (section 06 `PATCH /metadata`): edit the
 * three fields that stay mutable after publish (title, description, subject_tags).
 * Structure and lifecycle are never editable here, so the form exposes only these
 * inputs. Seeded from the current roadmap; Save calls the owner's edit action and
 * a failure surfaces a retry message without discarding the entered values.
 */
export function MetadataEditor({ roadmap, state, onSave, onCancel }: MetadataEditorProps) {
  const [title, setTitle] = useState(roadmap.title)
  const [description, setDescription] = useState(roadmap.description ?? '')
  const [tags, setTags] = useState((roadmap.subject_tags ?? []).join(', '))
  const isSaving = state.phase === 'saving'

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    void onSave({
      title: title.trim(),
      description: description.trim(),
      subject_tags: parseTags(tags),
    })
  }

  return (
    <form onSubmit={handleSubmit} className="rounded-lg border border-border bg-card p-4" aria-label="Edit roadmap details">
      <div className="space-y-4">
        <label className="block">
          <span className="text-sm font-medium text-foreground">Title</span>
          <Input
            className="mt-1"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            required
            disabled={isSaving}
          />
        </label>

        <label className="block">
          <span className="text-sm font-medium text-foreground">Description</span>
          <textarea
            className="mt-1 flex min-h-24 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            disabled={isSaving}
          />
        </label>

        <label className="block">
          <span className="text-sm font-medium text-foreground">Subject tags</span>
          <Input
            className="mt-1"
            value={tags}
            onChange={(event) => setTags(event.target.value)}
            placeholder="comma, separated, tags"
            disabled={isSaving}
          />
        </label>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={isSaving || title.trim().length === 0}>
          {isSaving ? 'Saving…' : 'Save details'}
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel} disabled={isSaving}>
          Cancel
        </Button>
      </div>

      {state.phase === 'failed' ? (
        <p className="mt-3 text-sm text-muted-foreground" role="alert">
          We couldn&rsquo;t save your changes. Please try again.
        </p>
      ) : null}
    </form>
  )
}
