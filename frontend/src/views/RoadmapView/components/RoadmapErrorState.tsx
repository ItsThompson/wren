interface RoadmapErrorStateProps {
  status: number | null
}

/**
 * The roadmap read failed. A 404/403 means the roadmap is not the caller's to
 * read (a private draft is invisible to non-owners; section 10 "Preview mode");
 * anything else is a generic load failure. Text-first, never color alone.
 */
export function RoadmapErrorState({ status }: RoadmapErrorStateProps) {
  const unreachable = status === 404 || status === 403
  return (
    <section className="reading-width py-16 text-center">
      <h1 className="display-m text-foreground">
        {unreachable ? 'Roadmap not found' : 'Something went wrong'}
      </h1>
      <p className="mx-auto mt-4 max-w-[42ch] text-muted-foreground">
        {unreachable
          ? 'This roadmap does not exist or is not shared with you.'
          : 'We could not load this roadmap. Please try again.'}
      </p>
    </section>
  )
}
