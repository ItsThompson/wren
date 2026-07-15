import { orderedSubsectionIds } from './ordering'
import type { Section } from './types'

function section(overrides: Partial<Section> = {}): Section {
  return {
    id: 'sec_a',
    title: 'A',
    subsections: {},
    subsection_order: [],
    ...overrides,
  }
}

describe('orderedSubsectionIds', () => {
  it('renders subsections in suggested_path order', () => {
    const sec = section({ subsection_order: ['sub_a', 'sub_b', 'sub_c'] })
    expect(orderedSubsectionIds(sec, ['sub_c', 'sub_a', 'sub_b'])).toEqual([
      'sub_c',
      'sub_a',
      'sub_b',
    ])
  })

  it('appends subsections missing from the path in their structural order', () => {
    const sec = section({ subsection_order: ['sub_a', 'sub_b', 'sub_c'] })
    // Only sub_b is sequenced; sub_a and sub_c fall back to structural order.
    expect(orderedSubsectionIds(sec, ['sub_b'])).toEqual(['sub_b', 'sub_a', 'sub_c'])
  })

  it('ignores path entries from other sections', () => {
    const sec = section({ subsection_order: ['sub_a'] })
    expect(orderedSubsectionIds(sec, ['sub_from_elsewhere', 'sub_a'])).toEqual(['sub_a'])
  })

  it('falls back to structural order when the path is empty', () => {
    const sec = section({ subsection_order: ['sub_a', 'sub_b'] })
    expect(orderedSubsectionIds(sec, [])).toEqual(['sub_a', 'sub_b'])
  })
})
