import { Button } from '@/components/ui/button'
import { WarningBanner } from './WarningBanner'

interface StaleRevisionNoticeProps {
  /** The server's recoverable detail, if any; a warm default otherwise. */
  detail?: string
  /** Refetch the current state so the user can continue from fresh data. */
  onReload: () => void
}

/**
 * The 409 `STALE_REVISION` re-read prompt (spec section 09 §3.4, section 12,
 * US-ERR-01). A first-class UI state, not a generic failure toast: an ochre
 * banner telling the user their view is stale, plus a refetch action to reload
 * before continuing.
 */
export function StaleRevisionNotice({ detail, onReload }: StaleRevisionNoticeProps) {
  return (
    <WarningBanner
      title="This roadmap changed. Reload to continue."
      action={
        <Button type="button" variant="outline" onClick={onReload}>
          Reload
        </Button>
      }
    >
      {detail ??
        'Someone updated this roadmap while you were working. Reload to pick up the latest version before making more changes.'}
    </WarningBanner>
  )
}
