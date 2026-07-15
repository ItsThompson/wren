import { Handle, Position, type NodeProps } from '@xyflow/react'

import type { TreeNode } from '../types'
import { DagNodeCard } from './DagNodeCard'

/**
 * React Flow custom node. Prerequisite edges connect into the
 * top handle and out of the bottom handle, giving the layered top-down layout.
 * The visible node is the presentational {@link DagNodeCard}; the handles are
 * the only React-Flow-specific wiring here.
 */
export function DagNode({ data }: NodeProps<TreeNode>) {
  return (
    <>
      <Handle type="target" position={Position.Top} className="!bg-border" />
      <DagNodeCard title={data.title} state={data.state} href={data.href} />
      <Handle type="source" position={Position.Bottom} className="!bg-border" />
    </>
  )
}
