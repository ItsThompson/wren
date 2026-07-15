/**
 * Loading skeleton for the roadmap preview (section 10 "Loading" state): a few
 * muted placeholder blocks standing in for the header and section cards.
 */
export function RoadmapSkeleton() {
  return (
    <section className="reading-width py-10" aria-busy="true" aria-label="Loading roadmap">
      <div className="h-9 w-2/3 animate-pulse rounded bg-muted" />
      <div className="mt-4 h-4 w-1/2 animate-pulse rounded bg-muted" />
      <div className="mt-10 space-y-4">
        <div className="h-24 animate-pulse rounded-lg bg-muted" />
        <div className="h-24 animate-pulse rounded-lg bg-muted" />
      </div>
    </section>
  )
}
