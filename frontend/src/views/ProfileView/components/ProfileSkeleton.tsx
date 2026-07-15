/**
 * The profile loading state: a name/handle header placeholder over a skeleton
 * card grid, matching the loaded layout so the swap is calm (section 10).
 */
export function ProfileSkeleton() {
  return (
    <section className="mx-auto max-w-[1120px] px-5 py-10">
      <div aria-label="Loading profile" className="animate-pulse">
        <div className="border-b border-border pb-6">
          <div className="h-9 w-64 rounded bg-muted" />
          <div className="mt-2 h-4 w-24 rounded bg-muted" />
        </div>
        <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((card) => (
            <div key={card} className="h-28 rounded-lg border border-border bg-card" />
          ))}
        </div>
      </div>
    </section>
  )
}
