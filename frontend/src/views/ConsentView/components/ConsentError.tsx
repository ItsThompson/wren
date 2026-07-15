import { ErrorState } from '@/components/states'

/**
 * The consent expired/error state (section 10 "Consent" error). Rendered when
 * the `auth_request_id` is missing, expired, or unknown: the parked request only
 * lives for a short window, so the recovery is to start over from the agent. Uses
 * the shared full-view error surface (text-first, never color alone).
 */
export function ConsentError() {
  return <ErrorState title="This request expired: reconnect from your agent." />
}
