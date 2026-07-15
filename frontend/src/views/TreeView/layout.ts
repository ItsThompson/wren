import dagre from 'dagre'

import type { Edge } from '@xyflow/react'

import type { TreeNode } from './types'

/** Fixed node box dagre lays out against; must match the rendered node width. */
const NODE_WIDTH = 208
const NODE_HEIGHT = 60

/**
 * Compute a layered top-down layout for the tree with dagre (spec section 08 /
 * section 11: React Flow + dagre is the recorded decision). Pure and DOM-free:
 * dagre positions nodes purely from the given fixed box size + prerequisite
 * edges, so this runs identically in the browser and under jsdom (no real layout
 * needed to test it).
 *
 * dagre anchors a node at its center; React Flow anchors at the top-left, so
 * each computed center is shifted back by half the node size.
 */
export function layoutTree(nodes: TreeNode[], edges: Edge[]): TreeNode[] {
  const graph = new dagre.graphlib.Graph()
  graph.setDefaultEdgeLabel(() => ({}))
  graph.setGraph({ rankdir: 'TB', ranksep: 64, nodesep: 40 })

  for (const node of nodes) {
    graph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT })
  }
  for (const edge of edges) {
    graph.setEdge(edge.source, edge.target)
  }

  dagre.layout(graph)

  return nodes.map((node) => {
    const { x, y } = graph.node(node.id)
    return {
      ...node,
      position: { x: x - NODE_WIDTH / 2, y: y - NODE_HEIGHT / 2 },
    }
  })
}
