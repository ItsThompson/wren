import { useParams } from 'react-router'

import { DraftPreview } from './components/DraftPreview'
import { RoadmapErrorState } from './components/RoadmapErrorState'
import { RoadmapListView } from './components/RoadmapListView'
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
 * and routes loading / error / loaded. A draft the caller owns renders in
 * read-only preview mode with the publish action (section 10 "Preview mode"); a
 * published roadmap renders the list view with progress tracking.
 */
export function RoadmapView({ baseUrl = API_BASE_URL }: RoadmapViewProps) {
  const { roadmapId } = useParams()
  const { state, publishState, publish } = useRoadmap(roadmapId ?? '', baseUrl)

  if (state.phase === 'loading') {
    return <RoadmapSkeleton />
  }
  if (state.phase === 'error') {
    return <RoadmapErrorState status={state.status} />
  }
  if (state.roadmap.status === 'draft') {
    return (
      <DraftPreview roadmap={state.roadmap} publishState={publishState} onPublish={publish} />
    )
  }
  return <RoadmapListView roadmap={state.roadmap} baseUrl={baseUrl} />
}
