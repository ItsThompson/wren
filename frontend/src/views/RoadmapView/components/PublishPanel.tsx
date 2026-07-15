import { Button } from '@/components/ui/button'
import type { PublishState, Roadmap } from '../types'

interface PublishPanelProps {
  status: Roadmap['status']
  publishState: PublishState
  onPublish: () => void
}

/**
 * The draft publish affordance (section 06 `:publish` action). On an owned draft
 * it offers a Publish action and, when a publish is hard-blocked (422), renders
 * the returned structural violations inline so the author sees the full fix list
 * in one pass. Once published it shows an immutable-published confirmation:
 * publish is one-way.
 */
export function PublishPanel({ status, publishState, onPublish }: PublishPanelProps) {
  if (status === 'published') {
    return (
      <section className="mt-8 rounded-lg border border-border bg-muted/40 p-4">
        <p className="text-sm font-medium text-foreground">Published</p>
        <p className="mt-1 text-sm text-muted-foreground">
          This roadmap is live. Its structure is now immutable.
        </p>
      </section>
    )
  }

  const isPublishing = publishState.phase === 'publishing'

  return (
    <section className="mt-8 border-t border-border pt-6">
      <div className="flex flex-wrap items-center gap-3">
        <Button type="button" onClick={onPublish} disabled={isPublishing}>
          {isPublishing ? 'Publishing…' : 'Publish'}
        </Button>
        <p className="text-sm text-muted-foreground">
          Publishing validates the structure, then makes the roadmap live and immutable.
        </p>
      </div>

      {publishState.phase === 'blocked' ? (
        <div className="mt-4" role="alert">
          <p className="text-sm font-medium text-foreground">
            This draft can’t be published yet. Fix {publishState.violations.length} issue(s):
          </p>
          <ul className="mt-2 space-y-1">
            {publishState.violations.map((violation) => (
              <li
                key={`${violation.rule}:${violation.ids.join(',')}`}
                className="text-sm text-muted-foreground"
              >
                <span className="font-mono text-xs text-foreground">{violation.rule}</span>{' '}
                {violation.message}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {publishState.phase === 'failed' ? (
        <p className="mt-4 text-sm text-muted-foreground" role="alert">
          We couldn’t publish this roadmap. Please try again.
        </p>
      ) : null}
    </section>
  )
}
