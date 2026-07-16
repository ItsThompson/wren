import type { Edge } from '@xyflow/react'

import { deriveNodeState } from '../node-state'
import { DAG_NODE_TYPE, type Roadmap, type Subsection, type TreeGraph, type TreeNode } from '../../types'

/**
 * Every subsection across all sections in a stable render order
 * (`section_order` -> `subsection_order`). This is the flatten used to seed both
 * the node list and the id index; dagre re-positions the nodes afterward, so the
 * order only needs to be deterministic.
 */
export function flattenSubsections(roadmap: Roadmap): Subsection[] {
  const sections = roadmap.sections ?? {}
  const flat: Subsection[] = []
  for (const sectionId of roadmap.section_order ?? []) {
    const section = sections[sectionId]
    if (!section) continue
    const subsections = section.subsections ?? {}
    for (const subsectionId of section.subsection_order ?? []) {
      const subsection = subsections[subsectionId]
      if (subsection) flat.push(subsection)
    }
  }
  return flat
}

/**
 * Build the tree graph from the roadmap document + the caller's checked set.
 * Subsections become nodes carrying their derived soft-state
 * and a list-view navigation target; `prereq_ids` become edges pointing from the
 * prerequisite down to the dependent (source = prereq, target = dependent) for
 * the layered top-down layout. Dangling prereq ids (targets of a removed node)
 * are dropped so a broken reference produces neither an edge nor a permanent
 * lock. Node positions are left at the origin for {@link layoutTree} to compute.
 */
export function buildTreeGraph(
  roadmap: Roadmap,
  checkedIds: Set<string>,
  roadmapId: string,
): TreeGraph {
  const ordered = flattenSubsections(roadmap)
  const index = new Map(ordered.map((subsection) => [subsection.id, subsection]))

  const nodes: TreeNode[] = ordered.map((subsection) => {
    const prereqs = (subsection.prereq_ids ?? []).flatMap((prereqId) => {
      const prereq = index.get(prereqId)
      return prereq ? [prereq] : []
    })
    return {
      id: subsection.id,
      type: DAG_NODE_TYPE,
      position: { x: 0, y: 0 },
      data: {
        title: subsection.title,
        state: deriveNodeState(subsection, prereqs, checkedIds),
        href: `/roadmaps/${roadmapId}#${subsection.id}`,
        subsectionId: subsection.id,
      },
    }
  })

  const edges: Edge[] = ordered.flatMap((subsection) =>
    (subsection.prereq_ids ?? []).flatMap((prereqId) =>
      index.has(prereqId)
        ? [{ id: `${prereqId}__${subsection.id}`, source: prereqId, target: subsection.id }]
        : [],
    ),
  )

  return { nodes, edges }
}
