import { useParams } from 'react-router'

import { useAuth } from '@/auth'
import { ImmutableNotice, StaleRevisionNotice } from '@/components/states'
import { isImmutable } from '@/lib/problem'
import { DraftPreview } from './components/DraftPreview'
import { RoadmapErrorState } from './components/RoadmapErrorState'
import { RoadmapListView } from './components/RoadmapListView'
import { RoadmapSkeleton } from './components/RoadmapSkeleton'
import { useRoadmap } from './hooks/useRoadmap'
import type { RoadmapActions } from './types'

/**
 * RoadmapView: fetches a roadmap by the route `:roadmapId`
 * and routes loading / error / loaded. A draft the caller owns renders in
 * read-only preview mode with the publish action; a
 * published roadmap renders the list view with progress tracking. Both surface
 * the fork action (any reader) and the owner-only presentation-metadata edit;
 * ownership is the signed-in user matching `roadmap.owner`. A 409
 * write conflict (stale re-read / immutable fork-to-change) surfaces as a shared
 * ochre prompt above the view.
 */
export function RoadmapView() {
  const { roadmapId } = useParams()
  const { user } = useAuth()
  const {
    state,
    publishState,
    publish,
    metadataState,
    editMetadata,
    forkState,
    fork,
    lifecycle,
    conflict,
    reload,
  } = useRoadmap(roadmapId ?? '')

  if (state.phase === 'loading') {
    return <RoadmapSkeleton />
  }
  if (state.phase === 'error') {
    return <RoadmapErrorState status={state.status} />
  }

  const isOwner = user?.id != null && user.id === state.roadmap.owner
  const actions: RoadmapActions = { metadataState, editMetadata, forkState, fork, lifecycle }

  // A 409 conflict is rendered above whichever view is showing. Immutable steers
  // to fork; anything else (stale) steers to a re-read via a full refetch.
  const conflictNotice = conflict ? (
    isImmutable(conflict) ? (
      <ImmutableNotice
        detail={conflict.detail}
        onFork={fork}
        forking={forkState.phase === 'forking'}
      />
    ) : (
      <StaleRevisionNotice detail={conflict.detail} onReload={reload} />
    )
  ) : null

  const view =
    state.roadmap.status === 'draft' ? (
      <DraftPreview
        roadmap={state.roadmap}
        publishState={publishState}
        onPublish={publish}
        isOwner={isOwner}
        actions={actions}
      />
    ) : (
      <RoadmapListView
        roadmap={state.roadmap}
        isOwner={isOwner}
        actions={actions}
        onReload={reload}
      />
    )

  return (
    <>
      {conflictNotice ? <div className="reading-width pt-6">{conflictNotice}</div> : null}
      {view}
    </>
  )
}
