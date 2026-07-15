/**
 * Loading skeleton for the connected-agents list (section 10 "Loading" state): a
 * couple of muted placeholder rows standing in for client cards.
 */
export function ConnectedClientsSkeleton() {
  return (
    <div className="flex flex-col gap-3" aria-busy="true" aria-label="Loading connected agents">
      <div className="h-20 animate-pulse rounded-lg bg-muted" />
      <div className="h-20 animate-pulse rounded-lg bg-muted" />
    </div>
  )
}
