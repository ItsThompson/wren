/**
 * The consent expired/error state (section 10 "Consent" error). Rendered when
 * the `auth_request_id` is missing, expired, or unknown: the parked request only
 * lives for a short window, so the recovery is to start over from the agent. One
 * calm Fraunces line, the empty-state pattern from the design language.
 */
export function ConsentError() {
  return (
    <section className="reading-width py-16 text-center">
      <p className="display-m mx-auto max-w-[24ch] text-foreground">
        This request expired: reconnect from your agent.
      </p>
    </section>
  )
}
