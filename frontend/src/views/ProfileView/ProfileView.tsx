import type { ReactNode } from 'react'
import { useParams } from 'react-router'

import { RoadmapCardGrid } from '@/components/RoadmapCardGrid'
import { Button } from '@/components/ui/button'
import { ProfileHeader } from './components/ProfileHeader'
import { ProfileNotFound } from './components/ProfileNotFound'
import { ProfileSkeleton } from './components/ProfileSkeleton'
import { useProfile } from './hooks/useProfile'

/**
 * Same-origin by default (dev proxy + MSW); prod points at the API subdomain via
 * `VITE_API_BASE_URL`. Read once at module load: the deployment base is fixed.
 */
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

interface ProfileViewProps {
  /** Overridable in tests; defaults to the deployment API base URL. */
  baseUrl?: string
}

/**
 * ProfileView (section 02 US-ACCT-03; design language §8): a user's public
 * profile at `/user/{handle}`. It renders the display name in Fraunces, the
 * handle in mono, and a grid of the user's published-public roadmap cards. An
 * unknown handle routes to a 404 view; loading / error / empty are handled too.
 * Public and viewer-agnostic: no session is required, and drafts / private /
 * archived roadmaps and the follow graph never appear.
 */
export function ProfileView({ baseUrl = API_BASE_URL }: ProfileViewProps) {
  const { handle } = useParams()
  const { state, reload } = useProfile(handle ?? '', baseUrl)

  if (state.phase === 'loading') {
    return <ProfileSkeleton />
  }
  if (state.phase === 'notfound') {
    return <ProfileNotFound handle={handle ?? ''} />
  }
  if (state.phase === 'error') {
    return (
      <section className="reading-width py-24 text-center">
        <p className="text-muted-foreground">We couldn&rsquo;t load this profile.</p>
        <div className="mt-6 flex justify-center">
          <Button variant="outline" onClick={reload}>
            Try again
          </Button>
        </div>
      </section>
    )
  }

  const roadmaps = state.profile.roadmaps ?? []
  let grid: ReactNode
  if (roadmaps.length === 0) {
    grid = (
      <div className="py-14 text-center">
        <p className="display-m text-foreground">No published roadmaps yet.</p>
      </div>
    )
  } else {
    grid = <RoadmapCardGrid roadmaps={roadmaps} />
  }

  return (
    <section className="mx-auto max-w-[1120px] px-5 py-10">
      <ProfileHeader displayName={state.profile.display_name} handle={state.profile.handle} />
      <div className="mt-8">{grid}</div>
    </section>
  )
}
