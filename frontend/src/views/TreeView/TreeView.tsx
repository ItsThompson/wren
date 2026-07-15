import { useMemo } from 'react'
import { Link, useParams } from 'react-router'

import { EmptyState, ErrorState } from '@/components/states'
import { TreeCanvas } from './components/TreeCanvas'
import { TreeHeader } from './components/TreeHeader'
import { TreeSkeleton } from './components/TreeSkeleton'
import { useTreeData } from './hooks/useTreeData'
import { layoutTree } from './layout'
import { buildTreeGraph } from './tree-graph'

/**
 * Same-origin by default (dev proxy + MSW); prod points at the API subdomain via
 * `VITE_API_BASE_URL`. Read once at module load: the deployment base is fixed.
 */
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

interface TreeViewProps {
  /** Overridable in tests; defaults to the deployment API base URL. */
  baseUrl?: string
}

/**
 * The Tree/DAG view: the roadmap's subsections
 * as a layered top-down DAG over their prerequisite edges (React Flow + dagre).
 * Node soft-state (done / available / locked) is derived from progress + prereqs
 * and shown by color + icon; clicking a node navigates to that subsection in the
 * list view. It owns its own roadmap + progress fetch and renders standalone at
 * `/roadmaps/{id}/tree` (a sibling route to the list view). Loading / empty /
 * error use the shared state surfaces so the tree reads like the rest of the app.
 */
export function TreeView({ baseUrl = API_BASE_URL }: TreeViewProps) {
  const { roadmapId } = useParams()
  const id = roadmapId ?? ''
  const { state } = useTreeData(id, baseUrl)

  const graph = useMemo(() => {
    if (state.phase !== 'loaded') return null
    const built = buildTreeGraph(state.roadmap, state.checkedIds, id)
    return { nodes: layoutTree(built.nodes, built.edges), edges: built.edges }
  }, [state, id])

  if (state.phase === 'loading') return <TreeSkeleton />

  if (state.phase === 'error') {
    // A 404/403 is indistinguishable by design (no-existence-leak convention);
    // a network failure lands here too. One calm dedicated view.
    return (
      <ErrorState
        title="Roadmap not found"
        description="This roadmap does not exist or is not shared with you."
        action={
          <Link to="/dashboard" className="text-primary underline-offset-4 hover:underline">
            Back to your dashboard
          </Link>
        }
      />
    )
  }

  return (
    <section className="mx-auto max-w-[1120px] px-4 py-8">
      <TreeHeader roadmapId={id} title={state.roadmap.title} />
      {graph && graph.nodes.length > 0 ? (
        <TreeCanvas graph={graph} />
      ) : (
        <EmptyState
          title="No nodes yet"
          description="This roadmap doesn’t have any subsections to map. Open the list view to add some."
        />
      )}
    </section>
  )
}
