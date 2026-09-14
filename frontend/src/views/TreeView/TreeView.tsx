import { useMemo } from 'react'
import { Link, useParams } from 'react-router'

import { EmptyState, ErrorState } from '@/components/states'
import { PageTitle } from '@/components/PageTitle'
import { useAuth } from '@/auth'
import { ReadOnlyNotice } from '@/views/RoadmapView/components/ReadOnlyNotice'
import { TreeCanvas } from './components/TreeCanvas'
import { TreeHeader } from './components/TreeHeader'
import { TreeSkeleton } from './components/TreeSkeleton'
import { useTreeData } from './hooks/useTreeData'
import { layoutTree } from './util/layout'
import { buildTreeGraph } from './util/tree-graph'

/**
 * The Tree/DAG view: the roadmap's subsections
 * as a layered top-down DAG over their prerequisite edges (React Flow + dagre).
 * Node soft-state (done / available / locked) is derived from progress + prereqs
 * and shown by color + icon; clicking a node navigates to that subsection in the
 * list view. It owns its own roadmap + progress fetch and renders standalone at
 * `/roadmaps/{id}/tree` (a sibling route to the list view). Loading / empty /
 * error use the shared state surfaces so the tree reads like the rest of the app.
 */
export function TreeView() {
  const { roadmapId } = useParams()
  const { status: authStatus } = useAuth()
  const id = roadmapId ?? ''
  const { state } = useTreeData(id)

  const graph = useMemo(() => {
    if (state.phase !== 'loaded') return null
    const built = buildTreeGraph(state.roadmap, state.checkedIds, id)
    return { nodes: layoutTree(built.nodes, built.edges), edges: built.edges }
  }, [state, id])

  if (state.phase === 'loading') {
    return (
      <>
        <PageTitle title="Roadmap" />
        <TreeSkeleton />
      </>
    )
  }

  if (state.phase === 'error') {
    // A 404/403 is indistinguishable by design (no-existence-leak convention);
    // a network failure lands here too. One calm dedicated view.
    return (
      <>
        <PageTitle title="Roadmap" />
        <ErrorState
          title="Roadmap not found"
          description="This roadmap does not exist or is not shared with you."
          action={
            <Link to="/dashboard" className="text-primary underline-offset-4 hover:underline">
              Back to your dashboard
            </Link>
          }
        />
      </>
    )
  }

  return (
    <>
      <PageTitle title={state.roadmap.title} />
      <section className="mx-auto max-w-[1120px] px-4 py-8">
        <TreeHeader roadmapId={id} title={state.roadmap.title} />
        {authStatus === 'anonymous' ? <ReadOnlyNotice /> : null}
        {state.progressState.phase === 'loading' ? (
          <p className="mt-4 text-sm text-muted-foreground" role="status">
            Loading progress…
          </p>
        ) : null}
        {state.progressState.phase === 'closed' ? (
          <p className="mt-4 text-sm text-muted-foreground" role="status">
            This archived roadmap is closed to new tracking. The tree remains available for reading.
          </p>
        ) : null}
        {state.progressState.phase === 'failed' ? (
          <p className="mt-4 text-sm text-muted-foreground" role="alert">
            We couldn’t load your progress. Node completion is unavailable.
          </p>
        ) : null}
        {graph && graph.nodes.length > 0 ? (
          <TreeCanvas graph={graph} />
        ) : (
          <EmptyState
            title="No nodes yet"
            description="This roadmap doesn’t have any subsections to map. Open the list view to add some."
          />
        )}
      </section>
    </>
  )
}
