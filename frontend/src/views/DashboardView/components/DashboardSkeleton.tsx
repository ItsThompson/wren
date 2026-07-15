/**
 * The dashboard loading state: a pair of titled section headers over skeleton
 * card rows, matching the loaded "Yours" / "Following" layout so the swap is
 * calm.
 */
export function DashboardSkeleton() {
  return (
    <div aria-label="Loading your dashboard" className="mt-8 animate-pulse space-y-10">
      {[0, 1].map((section) => (
        <div key={section}>
          <div className="h-6 w-32 rounded bg-muted" />
          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[0, 1, 2].map((card) => (
              <div key={card} className="h-28 rounded-lg border border-border bg-card" />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
