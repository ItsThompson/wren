import { describe, expect, it } from 'vitest'

import { layoutTree } from './layout'
import { DAG_NODE_TYPE, type TreeNode } from './types'

function buildNode(id: string): TreeNode {
  return {
    id,
    type: DAG_NODE_TYPE,
    position: { x: 0, y: 0 },
    data: { title: id, state: 'available', href: `/roadmaps/r#${id}`, subsectionId: id },
  }
}

describe('layoutTree', () => {
  it('assigns every node a finite position', () => {
    const nodes = [buildNode('a'), buildNode('b')]
    const edges = [{ id: 'a__b', source: 'a', target: 'b' }]
    const laid = layoutTree(nodes, edges)
    for (const node of laid) {
      expect(Number.isFinite(node.position.x)).toBe(true)
      expect(Number.isFinite(node.position.y)).toBe(true)
    }
  })

  it('lays prerequisites out above their dependents (layered top-down)', () => {
    const nodes = [buildNode('a'), buildNode('b'), buildNode('c')]
    const edges = [
      { id: 'a__b', source: 'a', target: 'b' },
      { id: 'b__c', source: 'b', target: 'c' },
    ]
    const positionById = Object.fromEntries(
      layoutTree(nodes, edges).map((node) => [node.id, node.position]),
    )
    // Top-down (rankdir TB): a is above b is above c.
    expect(positionById.a.y).toBeLessThan(positionById.b.y)
    expect(positionById.b.y).toBeLessThan(positionById.c.y)
  })

  it('spreads sibling dependents of the same prerequisite apart horizontally', () => {
    const nodes = [buildNode('root'), buildNode('left'), buildNode('right')]
    const edges = [
      { id: 'root__left', source: 'root', target: 'left' },
      { id: 'root__right', source: 'root', target: 'right' },
    ]
    const positionById = Object.fromEntries(
      layoutTree(nodes, edges).map((node) => [node.id, node.position]),
    )
    // Same rank, so they share a row but occupy different columns.
    expect(positionById.left.y).toBe(positionById.right.y)
    expect(positionById.left.x).not.toBe(positionById.right.x)
  })

  it('does not mutate the input nodes', () => {
    const nodes = [buildNode('a')]
    layoutTree(nodes, [])
    expect(nodes[0].position).toEqual({ x: 0, y: 0 })
  })
})
