import { describe, expect, it } from 'vitest'

import { deriveNodeState } from './node-state'
import { NODE_STATE, type Subsection } from './types'

/** A minimal subsection; `item_order` drives the derived done-state. */
function buildSubsection(overrides: Partial<Subsection> = {}): Subsection {
  return {
    id: 'sub',
    title: 'Subsection',
    prereq_ids: [],
    item_order: ['item-1'],
    checklist_items: { 'item-1': { id: 'item-1', text: 'Do the thing' } },
    ...overrides,
  }
}

describe('deriveNodeState', () => {
  it('is done when all of the subsection own items are checked', () => {
    const subsection = buildSubsection({ item_order: ['a', 'b'] })
    const state = deriveNodeState(subsection, [], new Set(['a', 'b']))
    expect(state).toBe(NODE_STATE.Done)
  })

  it('is available when it is not done and it has no prerequisites', () => {
    const subsection = buildSubsection({ item_order: ['a'] })
    const state = deriveNodeState(subsection, [], new Set())
    expect(state).toBe(NODE_STATE.Available)
  })

  it('is available when it is not done and every prerequisite is done', () => {
    const prereq = buildSubsection({ id: 'p', item_order: ['p1'] })
    const subsection = buildSubsection({ id: 's', item_order: ['s1'] })
    const state = deriveNodeState(subsection, [prereq], new Set(['p1']))
    expect(state).toBe(NODE_STATE.Available)
  })

  it('is locked when it is not done and a prerequisite is not yet done', () => {
    const donedPrereq = buildSubsection({ id: 'p1', item_order: ['p1-a'] })
    const openPrereq = buildSubsection({ id: 'p2', item_order: ['p2-a'] })
    const subsection = buildSubsection({ id: 's', item_order: ['s1'] })
    const state = deriveNodeState(subsection, [donedPrereq, openPrereq], new Set(['p1-a']))
    expect(state).toBe(NODE_STATE.Locked)
  })

  it('reads done even when a prerequisite is not done (done takes precedence)', () => {
    const openPrereq = buildSubsection({ id: 'p', item_order: ['p1'] })
    const subsection = buildSubsection({ id: 's', item_order: ['s1'] })
    const state = deriveNodeState(subsection, [openPrereq], new Set(['s1']))
    expect(state).toBe(NODE_STATE.Done)
  })

  it('treats a subsection with no items as not-done (matches the list view)', () => {
    const subsection = buildSubsection({ item_order: [] })
    const state = deriveNodeState(subsection, [], new Set())
    expect(state).toBe(NODE_STATE.Available)
  })
})
