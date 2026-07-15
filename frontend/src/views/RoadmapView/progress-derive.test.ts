import { isSubsectionDone, overallCount, sectionCount } from './progress-derive'
import type { Roadmap, Section, Subsection } from './types'

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
