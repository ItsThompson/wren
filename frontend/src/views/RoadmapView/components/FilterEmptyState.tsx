import { Button } from '@/components/ui/button'

interface FilterEmptyStateProps {
  onClear: () => void
}

/** A quiet sans-serif result state for an active filter with no matches. */
export function FilterEmptyState({ onClear }: FilterEmptyStateProps) {
  return (
    <section
      className="mt-10 rounded-lg border border-border bg-card px-6 py-10 text-center"
      role="group"
      aria-label="Filter results"
    >
      <h2 className="text-lg font-medium text-foreground">No topics match these filters</h2>
      <p className="mt-2 text-sm text-muted-foreground">Clear the selected tags to see every topic again.</p>
      <Button type="button" className="mt-5" onClick={onClear}>
        Clear filters
      </Button>
    </section>
  )
}
