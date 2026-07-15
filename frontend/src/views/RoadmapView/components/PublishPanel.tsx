import { ViolationList } from '@/components/states'
import { Button } from '@/components/ui/button'
import type { PublishState } from '../types'

interface PublishPanelProps {
  publishState: PublishState
  onPublish: () => void
}

/**
 * The draft publish affordance (section 06 `:publish` action). Offers a Publish
 * action and, when a publish is hard-blocked (422), renders the returned
 * structural violations via the shared ochre `ViolationList` so the author sees
 * the full fix list (rule + message + offending ids) in one pass (US-ERR-02).
 * Rendered only in draft preview mode: on a successful publish the RoadmapView
 * routes to the published list view, so there is no published state here.
 */
export function PublishPanel({ publishState, onPublish }: PublishPanelProps) {
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
        <div className="mt-4">
          <ViolationList violations={publishState.violations} />
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
