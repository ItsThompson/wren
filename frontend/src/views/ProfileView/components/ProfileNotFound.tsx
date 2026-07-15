import { Link } from 'react-router'

import { Button } from '@/components/ui/button'

interface ProfileNotFoundProps {
  handle: string
}

/**
 * The 404 view for an unknown handle (section 02 US-ACCT-03; section 10 Profile
 * error state). Uses the empty-state pattern (a Fraunces line, a muted sub-line
 * naming the missing handle, one primary action back home).
 */
export function ProfileNotFound({ handle }: ProfileNotFoundProps) {
  return (
    <section className="reading-width py-24 text-center">
      <p className="display-m text-foreground">No such profile.</p>
      <p className="mx-auto mt-3 max-w-[44ch] text-muted-foreground">
        We couldn&rsquo;t find anyone with the handle{' '}
        <span className="font-mono text-foreground">@{handle}</span>.
      </p>
      <div className="mt-6 flex justify-center">
        <Button asChild>
          <Link to="/">Back to Wren</Link>
        </Button>
      </div>
    </section>
  )
}
