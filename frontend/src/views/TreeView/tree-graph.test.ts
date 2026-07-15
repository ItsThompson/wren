import { describe, expect, it } from 'vitest'

import { buildTreeGraph, flattenSubsections } from './tree-graph'
import { DAG_NODE_TYPE, NODE_STATE, type Roadmap } from './types'

const ROADMAP_ID = 'grokking-dsa-7f3k'

/**
 * A published roadmap with two sections and a prerequisite chain a -> b -> c,
 * plus a dangling prereq id on c to exercise the drop-broken-edges guard.
 */
function buildRoadmap(): Roadmap {
  return {
    id: ROADMAP_ID,
    owner: 'user-1',
    title: 'Grokking DSA',
    visibility: 'public',
    status: 'published',
    revision: 3,
    section_order: ['sec_1', 'sec_2'],
    sections: {
      sec_1: {
        id: 'sec_1',
        title: 'Foundations',
        subsection_order: ['a', 'b'],
        subsections: {
          a: { id: 'a', title: 'Arrays', prereq_ids: [], item_order: ['a1'] },
          b: { id: 'b', title: 'Hashing', prereq_ids: ['a'], item_order: ['b1'] },
        },
      },
      sec_2: {
        id: 'sec_2',
        title: 'Trees',
        subsection_order: ['c'],
        subsections: {
          c: { id: 'c', title: 'Binary trees', prereq_ids: ['b', 'ghost'], item_order: ['c1'] },
        },
      },
    },
    created_at: '2026-07-15T00:00:00Z',
    updated_at: '2026-07-15T00:00:00Z',
  }
}

describe('flattenSubsections', () => {
  it('walks section_order then subsection_order in a stable order', () => {
    const ids = flattenSubsections(buildRoadmap()).map((subsection) => subsection.id)
    expect(ids).toEqual(['a', 'b', 'c'])
  })
})

describe('buildTreeGraph', () => {
  it('builds one node per subsection with the dag node type and list-view href', () => {
    const { nodes } = buildTreeGraph(buildRoadmap(), new Set(), ROADMAP_ID)
    expect(nodes.map((node) => node.id)).toEqual(['a', 'b', 'c'])
    expect(nodes.every((node) => node.type === DAG_NODE_TYPE)).toBe(true)
    expect(nodes[0].data.href).toBe(`/roadmaps/${ROADMAP_ID}#a`)
    expect(nodes[0].data.title).toBe('Arrays')
    expect(nodes[0].data.subsectionId).toBe('a')
  })

  it('builds prereq edges pointing prereq -> dependent and drops dangling ids', () => {
    const { edges } = buildTreeGraph(buildRoadmap(), new Set(), ROADMAP_ID)
    // a -> b and b -> c; c's dangling "ghost" prereq produces no edge.
    expect(edges.map((edge) => `${edge.source}->${edge.target}`)).toEqual(['a->b', 'b->c'])
  })

  it('derives soft-state from progress: no progress leaves roots available, rest locked', () => {
    const { nodes } = buildTreeGraph(buildRoadmap(), new Set(), ROADMAP_ID)
    const stateById = Object.fromEntries(nodes.map((node) => [node.id, node.data.state]))
    expect(stateById).toEqual({
      a: NODE_STATE.Available,
      b: NODE_STATE.Locked,
      c: NODE_STATE.Locked,
    })
  })

  it('unlocks a dependent once its prerequisite is done', () => {
    const { nodes } = buildTreeGraph(buildRoadmap(), new Set(['a1']), ROADMAP_ID)
    const stateById = Object.fromEntries(nodes.map((node) => [node.id, node.data.state]))
    expect(stateById).toEqual({
      a: NODE_STATE.Done,
      b: NODE_STATE.Available,
      c: NODE_STATE.Locked,
    })
  })

  it('returns an empty graph for a roadmap with no sections', () => {
    const empty = { ...buildRoadmap(), section_order: [], sections: {} }
    const graph = buildTreeGraph(empty, new Set(), ROADMAP_ID)
    expect(graph.nodes).toEqual([])
    expect(graph.edges).toEqual([])
  })
})
