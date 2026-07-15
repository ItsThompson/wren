import { isSubsectionDone } from '@/views/RoadmapView/progress-derive'

import { NODE_STATE, type NodeState, type Subsection } from './types'

/**
 * Derive a tree node's soft state from the caller's progress (spec section 08 /
 * ticket 24):
 *
 * - **done**: the subsection's own items are all checked. Delegates to the list
 *   view's canonical `isSubsectionDone`, so the tree and list always agree on
 *   what "done" means (done is derived from the progress record, never stored).
 * - **available**: not done, and every resolvable prerequisite is done.
 * - **locked**: not done, and at least one prerequisite is not yet done.
 *
 * `done` takes precedence over prereq state: a subsection whose own items are
 * all checked reads as done regardless of its prerequisites.
 *
 * `prereqs` is the list of RESOLVED prerequisite subsections; the caller drops
 * dangling prereq ids so a broken edge can never lock a node forever. State is
 * presentational only: there is no gating, so a locked node stays clickable.
 *
 * Divergence (intentional, bounded): dropping dangling prereqs means a node
 * whose only prereqs are broken reads as `available` here, whereas the backend
 * `get_next` treats an unresolved prereq as unsatisfiable. This can only differ
 * on drafts, which are preview-only with no progress; publish-time V2 validation
 * forbids dangling edges, so a published roadmap has none and the two agree.
 * Mirroring the backend here is optional.
 */
export function deriveNodeState(
  subsection: Subsection,
  prereqs: Subsection[],
  checkedIds: Set<string>,
): NodeState {
  if (isSubsectionDone(subsection, checkedIds)) return NODE_STATE.Done
  const prereqsSatisfied = prereqs.every((prereq) => isSubsectionDone(prereq, checkedIds))
  return prereqsSatisfied ? NODE_STATE.Available : NODE_STATE.Locked
}
