import { useParams } from 'react-router'

import { DraftPreview } from './components/DraftPreview'
import { RoadmapErrorState } from './components/RoadmapErrorState'
import { RoadmapSkeleton } from './components/RoadmapSkeleton'
import { useRoadmap } from './hooks/useRoadmap'

/**
 * Same-origin by default (dev proxy + MSW); prod points at the API subdomain via
 * `VITE_API_BASE_URL`. Read once at module load: the deployment base is fixed.
 */
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

interface RoadmapViewProps {
  /** Overridable in tests; defaults to the deployment API base URL. */
  baseUrl?: string
}

/**
 * RoadmapView (section 10 view tree): fetches a roadmap by the route `:roadmapId`
 * and routes the three states (loading / error / loaded). For this slice the
 * loaded state is the owned-draft list preview; the tree tab and published
 * progress views arrive in later slices.
 */
export function RoadmapView({ baseUrl = API_BASE_URL }: RoadmapViewProps) {
  const { roadmapId } = useParams()
  const { state } = useRoadmap(roadmapId ?? '', baseUrl)

  if (state.phase === 'loading') {
    return <RoadmapSkeleton />
  }
  if (state.phase === 'error') {
    return <RoadmapErrorState status={state.status} />
  }
  return <DraftPreview roadmap={state.roadmap} />
}
