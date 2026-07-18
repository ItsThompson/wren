import { ArrowRight } from 'lucide-react'
import { Link } from 'react-router'

import { Button } from '@/components/ui/button'
import { useStartDestination } from '../hooks/useStartDestination'

/**
 * The page's single primary CTA, reused in the hero and the final band. It
 * resolves its own auth-aware href; while the session is still resolving it
 * renders disabled (never a link to signup) so a returning authenticated
 * visitor is not bounced through `/auth`. Keeps the default terracotta variant.
 */
export function StartRoadmapButton() {
  const destination = useStartDestination()

  if (destination === null) {
    return (
      <Button size="lg" disabled>
        Start a roadmap
        <ArrowRight />
      </Button>
    )
  }

  return (
    <Button size="lg" asChild>
      <Link to={destination}>
        Start a roadmap
        <ArrowRight />
      </Link>
    </Button>
  )
}
