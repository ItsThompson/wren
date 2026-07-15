import { Button } from '@/components/ui/button'
import { WarningBanner } from './WarningBanner'

interface ImmutableNoticeProps {
  /** The server's recoverable detail, if any; a warm default otherwise. */
  detail?: string
  /** Fork the roadmap into an editable private draft; omit to hide the action. */
  onFork?: () => void
  /** Whether a fork is in flight (disables + relabels the action). */
  forking?: boolean
}

/**
 * The 409 `IMMUTABLE` prompt: a structural write
 * against a published/archived roadmap is refused because published roadmaps are
 * immutable (followers' progress stays stable). The recovery is to fork it into a
 * private draft you can edit and publish.
 */
export function ImmutableNotice({ detail, onFork, forking = false }: ImmutableNoticeProps) {
  return (
    <WarningBanner
      title="This roadmap is published. Fork it to make changes."
      action={
        onFork ? (
          <Button type="button" variant="outline" onClick={onFork} disabled={forking}>
            {forking ? 'Forking…' : 'Fork to change'}
          </Button>
        ) : undefined
      }
    >
      {detail ??
        'Published roadmaps are immutable so followers keep stable progress. Fork it into a private draft to edit and publish your own copy.'}
    </WarningBanner>
  )
}
