import { Link } from 'react-router'

import { Button } from '@/components/ui/button'

/**
 * Generic catch-all for unmatched routes. Uses the empty-state pattern (§7.8):
 * a Fraunces line, a muted sub-line, and one primary action back home.
 */
export function NotFoundView() {
  return (
    <section className="reading-width py-24 text-center">
      <p className="display-m text-foreground">This page isn&rsquo;t here.</p>
      <p className="mx-auto mt-2 max-w-[46ch] text-muted-foreground">
        The page you&rsquo;re looking for doesn&rsquo;t exist yet.
      </p>
      <div className="mt-6 flex justify-center">
        <Button asChild>
          <Link to="/">Back to Wren</Link>
        </Button>
      </div>
    </section>
  )
}
