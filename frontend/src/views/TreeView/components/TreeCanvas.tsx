import { Background, Controls, ReactFlow } from '@xyflow/react'

import { DAG_NODE_TYPE, type TreeGraph } from '../types'
import { DagNode } from './DagNode'

import '@xyflow/react/dist/style.css'

/**
 * Registered once at module scope: React Flow warns (and re-mounts nodes) if
 * `nodeTypes` is a fresh object on every render.
 */
const nodeTypes = { [DAG_NODE_TYPE]: DagNode }

interface TreeCanvasProps {
  graph: TreeGraph
}

/**
 * The React Flow surface for the tree (spec section 08 / section 11). Read-only
 * exploration: nodes are not draggable, connectable, or selectable (the layout
 * is dagre-computed, not user-edited), and `fitView` frames the whole layered
 * graph. Navigation lives in each node's link (see {@link DagNodeCard}), not an
 * `onNodeClick` handler, so native link behavior is preserved.
 */
export function TreeCanvas({ graph }: TreeCanvasProps) {
  return (
    <div className="h-[70vh] w-full overflow-hidden rounded-lg border border-border bg-card">
      <ReactFlow
        nodes={graph.nodes}
        edges={graph.edges}
        nodeTypes={nodeTypes}
        fitView
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        edgesFocusable={false}
      >
        <Background />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  )
}
