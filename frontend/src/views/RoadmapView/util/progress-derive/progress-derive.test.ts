import { isSubsectionDone, overallCount, sectionCount } from './progress-derive'
import { firstNextSubsectionId, patchCheckedIds, patchDeadline } from './progress-derive'
import type { NextResult, ProgressSnapshot, Roadmap, Section, Subsection } from '../../types'

/** A subsection with the given item ids and no resources. */
function subsection(id: string, itemIds: string[]): Subsection {
  return {
    id,
    title: id,
    tags: [],
    prereq_ids: [],
    resource_order: [],
    resources: {},
    item_order: itemIds,
    checklist_items: Object.fromEntries(itemIds.map((itemId) => [itemId, { id: itemId, text: itemId }])),
  }
}

function section(id: string, subsections: Subsection[]): Section {
  return {
    id,
    title: id,
    subsection_order: subsections.map((sub) => sub.id),
    subsections: Object.fromEntries(subsections.map((sub) => [sub.id, sub])),
  }
}

function roadmap(sections: Section[]): Roadmap {
  return {
    id: 'r-0000',
    owner: 'owner',
    title: 'R',
    subject_tags: [],
    visibility: 'public',
    status: 'published',
    revision: 1,
    section_order: sections.map((sec) => sec.id),
    sections: Object.fromEntries(sections.map((sec) => [sec.id, sec])),
    suggested_path: [],
    created_at: '2026-07-15T00:00:00Z',
    updated_at: '2026-07-15T00:00:00Z',
  }
}

const SUB_A = subsection('sub_a', ['chk_a1', 'chk_a2'])
const SUB_B = subsection('sub_b', ['chk_b1'])
const SUB_C = subsection('sub_c', ['chk_c1'])
const FOUNDATIONS = section('sec_f', [SUB_A, SUB_B])
const ADVANCED = section('sec_g', [SUB_C])
const ROADMAP = roadmap([FOUNDATIONS, ADVANCED])

describe('isSubsectionDone', () => {
  it('is true only when every item is checked', () => {
    expect(isSubsectionDone(SUB_A, new Set(['chk_a1', 'chk_a2']))).toBe(true)
    expect(isSubsectionDone(SUB_A, new Set(['chk_a1']))).toBe(false)
  })

  it('is false for a subsection with no items', () => {
    expect(isSubsectionDone(subsection('sub_empty', []), new Set())).toBe(false)
  })
})

describe('sectionCount', () => {
  it('counts checked items within the section', () => {
    expect(sectionCount(FOUNDATIONS, new Set(['chk_a1', 'chk_a2']))).toEqual({
      total: 3,
      checked: 2,
      percent: 67,
    })
  })

  it('is zero percent with no items checked', () => {
    expect(sectionCount(ADVANCED, new Set())).toEqual({ total: 1, checked: 0, percent: 0 })
  })
})

describe('overallCount', () => {
  it('sums across all sections', () => {
    expect(overallCount(ROADMAP, new Set(['chk_a1', 'chk_a2', 'chk_b1']))).toEqual({
      total: 4,
      checked: 3,
      percent: 75,
    })
  })

  it('ignores checked ids that are not in the roadmap', () => {
    expect(overallCount(ROADMAP, new Set(['chk_ghost']))).toEqual({
      total: 4,
      checked: 0,
      percent: 0,
    })
  })
})

describe('firstNextSubsectionId', () => {
  it('returns the first item\'s subsection id', () => {
    const next: NextResult = {
      items: [
        { subsection_id: 'sub_arrays', item_id: 'chk_read', text: 'Read', why_now: 'first' },
        { subsection_id: 'sub_hashing', item_id: 'chk_hash', text: 'Impl', why_now: 'later' },
      ],
      remaining_in_path: 2,
      complete: false,
    }
    expect(firstNextSubsectionId(next)).toBe('sub_arrays')
  })

  it('returns null when there are no items (path complete)', () => {
    expect(firstNextSubsectionId({ items: [], remaining_in_path: 0, complete: true })).toBeNull()
  })

  it('returns null when items is absent', () => {
    expect(firstNextSubsectionId({ remaining_in_path: 0, complete: false })).toBeNull()
  })

  it('returns null for an undefined response (read not resolved / failed)', () => {
    expect(firstNextSubsectionId(undefined)).toBeNull()
  })
})

describe('patchCheckedIds', () => {
  /** A snapshot carrying the given checked ids. */
  function snapshot(checkedIds: string[]): ProgressSnapshot {
    return { roadmap_id: 'r-0000', total_items: 3, checked_items: checkedIds.length, percent: 0, checked_ids: checkedIds }
  }

  it('adds an id when checking', () => {
    expect(patchCheckedIds(snapshot(['chk_a1']), 'r-0000', 'chk_a2', true).checked_ids).toEqual([
      'chk_a1',
      'chk_a2',
    ])
  })

  it('removes an id when unchecking', () => {
    expect(patchCheckedIds(snapshot(['chk_a1', 'chk_a2']), 'r-0000', 'chk_a1', false).checked_ids).toEqual([
      'chk_a2',
    ])
  })

  it('is idempotent when re-checking an already-checked id', () => {
    expect(patchCheckedIds(snapshot(['chk_a1']), 'r-0000', 'chk_a1', true).checked_ids).toEqual([
      'chk_a1',
    ])
  })

  it('preserves the other snapshot fields (deadline is not clobbered)', () => {
    const withDeadline: ProgressSnapshot = { ...snapshot([]), deadline: '2026-12-01' }
    expect(patchCheckedIds(withDeadline, 'r-0000', 'chk_a1', true).deadline).toBe('2026-12-01')
  })

  it('seeds a conforming snapshot when none has resolved yet', () => {
    const patched = patchCheckedIds(undefined, 'r-0000', 'chk_a1', true)
    expect(patched).toEqual({
      roadmap_id: 'r-0000',
      total_items: 0,
      checked_items: 0,
      percent: 0,
      checked_ids: ['chk_a1'],
    })
  })
})

describe('patchDeadline', () => {
  /** A snapshot carrying the given checked ids. */
  function snapshot(checkedIds: string[]): ProgressSnapshot {
    return { roadmap_id: 'r-0000', total_items: 3, checked_items: checkedIds.length, percent: 0, checked_ids: checkedIds }
  }

  it('sets the deadline while preserving checked_ids', () => {
    const patched = patchDeadline(snapshot(['chk_a1']), 'r-0000', '2026-12-01')
    expect(patched.deadline).toBe('2026-12-01')
    expect(patched.checked_ids).toEqual(['chk_a1'])
  })

  it('clears the deadline with null', () => {
    const patched = patchDeadline({ ...snapshot([]), deadline: '2026-12-01' }, 'r-0000', null)
    expect(patched.deadline).toBeNull()
  })

  it('seeds a conforming snapshot when none has resolved yet', () => {
    expect(patchDeadline(undefined, 'r-0000', '2026-12-01')).toEqual({
      roadmap_id: 'r-0000',
      total_items: 0,
      checked_items: 0,
      percent: 0,
      checked_ids: [],
      deadline: '2026-12-01',
    })
  })
})
