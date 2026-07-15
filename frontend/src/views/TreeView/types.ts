import type { Edge, Node } from '@xyflow/react'

import type { components } from '@/api'

/**
 * Tree-view read types, sourced from the OpenAPI-generated client (never
 * hand-written; section 06/10 codegen contract). The tree consumes the full
 * `GET /roadmaps/{id}` document (subsections carry `prereq_ids`, the DAG edges)
 * plus the caller's progress snapshot for done-state.
 */
export type Roadmap = components['schemas']['Roadmap']
export type Subsection = components['schemas']['Subsection']
export type ProgressSnapshot = components['schemas']['ProgressSnapshot']

/**
 * The soft visual state of a tree node. This is a const
 * map + derived union rather than a TS `enum`: the app tsconfig sets
 * `erasableSyntaxOnly`, which forbids enums.
 */
export const NODE_STATE = {
  Done: 'done',
  Available: 'available',
  Locked: 'locked',
} as const

export type NodeState = (typeof NODE_STATE)[keyof typeof NODE_STATE]

/** The single React Flow node type registered for subsection nodes. */
export const DAG_NODE_TYPE = 'dagNode'

/**
 * The data each React Flow node carries. Declared as a `type` (object literal,
 * so it gets the implicit index signature) rather than an `interface`, because
 * React Flow's `Node<T>` constrains `T extends Record<string, unknown>` and an
 * interface has no implicit index signature.
 */
export type TreeNodeData = {
  title: string
  state: NodeState
  /** List-view target for click-navigation: `/roadmaps/{id}#{subsectionId}`. */
  href: string
  subsectionId: string
}

export type TreeNode = Node<TreeNodeData, typeof DAG_NODE_TYPE>

/** The built graph handed to React Flow: positioned nodes + prerequisite edges. */
export interface TreeGraph {
  nodes: TreeNode[]
  edges: Edge[]
}

/**
 * The tree-view fetch state as a single discriminated union so an impossible
 * "loaded with an error" combination cannot arise (frontend state-structure
 * rule). Progress is folded into the loaded state as the caller's `checkedIds`.
 */
export type TreeDataState =
  | { phase: 'loading' }
  | { phase: 'error' }
  | { phase: 'loaded'; roadmap: Roadmap; checkedIds: Set<string> }
