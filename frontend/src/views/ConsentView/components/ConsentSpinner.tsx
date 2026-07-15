import { Loader2 } from 'lucide-react'

/**
 * The consent loading state: a quiet spinner while the parked
 * request's context resolves. The trust moment stays calm, never loud.
 */
export function ConsentSpinner() {
  return (
    <section
      className="reading-width flex min-h-[50vh] items-center justify-center py-16"
      role="status"
      aria-label="Loading consent request"
    >
      <Loader2 className="size-6 animate-spin text-muted-foreground" aria-hidden="true" />
    </section>
  )
}
