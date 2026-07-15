import { Link } from 'react-router'

import { ErrorState } from '@/components/states'

interface RoadmapErrorStateProps {
  status: number | null
}

/**
 * The roadmap read failed. A 404/403 means the roadmap is not the caller's to
 * read (a private draft is invisible to non-owners; section 10 "Preview mode"),
 * and both render the SAME dedicated view so a private roadmap's existence never
 * leaks (US-ERR-04, no-existence-leak convention); anything else is a generic
 * load failure. Uses the shared text-first `ErrorState` (never color alone).
 */
export function RoadmapErrorState({ status }: RoadmapErrorStateProps) {
  const unreachable = status === 404 || status === 403
  return (
    <ErrorState
      title={unreachable ? 'Roadmap not found' : 'Something went wrong'}
      description={
        unreachable
          ? 'This roadmap does not exist or is not shared with you.'
          : 'We could not load this roadmap. Please try again.'
      }
      action={
        <Link to="/dashboard" className="text-primary underline-offset-4 hover:underline">
          Back to your dashboard
        </Link>
      }
    />
  )
}
