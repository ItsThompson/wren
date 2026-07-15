/**
 * Loading placeholder for the tree view. Ticket 26 harmonizes the loading
 * pattern across every view; this is the basic in-view state until then.
 */
export function TreeSkeleton() {
  return (
    <section
      aria-busy="true"
      aria-label="Loading roadmap tree"
      className="mx-auto max-w-[1120px] px-4 py-8"
    >
      <div className="mb-6 h-8 w-56 animate-pulse rounded-md bg-muted" />
      <div className="h-[70vh] w-full animate-pulse rounded-lg border border-border bg-muted/50" />
    </section>
  )
}
