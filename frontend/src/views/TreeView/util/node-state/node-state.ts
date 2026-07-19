import { isSubsectionDone } from '@/views/RoadmapView/util/progress-derive'

import { NODE_STATE, type NodeState, type Subsection } from '../../types'

/**
 * Derive a tree node's soft state from the caller's progress:
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
 * Dropping dangling prereqs makes a node with only-broken prereqs read as
 * `available` here (the backend `get_next` treats it as unsatisfiable). This
 * can only differ on drafts (preview-only, no progress); publish-time
 * validation forbids dangling edges, so published roadmaps agree.
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
