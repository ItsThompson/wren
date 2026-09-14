import { collectTrackTags, deriveTrackTagMatches } from './track-tags'
import type { Roadmap, Section, Subsection } from '../../types'

function subsection(id: string, tags: string[]): Subsection {
  return {
    id,
    title: id,
    tags,
    prereq_ids: [],
    resource_order: [],
    resources: {},
    item_order: [],
    checklist_items: {},
  }
}

function roadmap(sections: Section[], sectionOrder?: string[]): Roadmap {
  return {
    id: 'r1',
    owner: 'u1',
    title: 'R',
    subject_tags: ['subject-not-a-track-tag'],
    published_visibility: 'public',
    status: 'published',
    revision: 1,
    section_order: sectionOrder ?? sections.map((section) => section.id),
    suggested_path: [],
    sections: Object.fromEntries(sections.map((section) => [section.id, section])),
    created_at: '2026-07-15T00:00:00Z',
    updated_at: '2026-07-15T00:00:00Z',
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

describe('collectTrackTags', () => {
  it('collects distinct track tags in first-appearance order', () => {
    const model = roadmap([
      section('s1', [subsection('a', ['arrays', 'hashing']), subsection('b', ['graphs'])]),
      section('s2', [subsection('c', ['trees'])]),
    ])
    expect(collectTrackTags(model)).toEqual(['arrays', 'hashing', 'graphs', 'trees'])
  })

  it('deduplicates a tag shared by multiple subsections, keeping the first position', () => {
    const model = roadmap([
      section('s1', [subsection('a', ['graphs']), subsection('b', ['graphs', 'trees'])]),
    ])
    expect(collectTrackTags(model)).toEqual(['graphs', 'trees'])
  })

  it('honors section_order and subsection_order for appearance order', () => {
    const model = roadmap(
      [
        section('s1', [subsection('a', ['later'])]),
        section('s2', [subsection('b', ['earlier'])]),
      ],
      ['s2', 's1'],
    )
    expect(collectTrackTags(model)).toEqual(['earlier', 'later'])
  })

  it('never includes roadmap-level subject tags', () => {
    const model = roadmap([section('s1', [subsection('a', ['arrays'])])])
    expect(collectTrackTags(model)).toEqual(['arrays'])
    expect(collectTrackTags(model)).not.toContain('subject-not-a-track-tag')
  })

  it('returns an empty list when no subsection has a track tag', () => {
    const model = roadmap([section('s1', [subsection('a', [])])])
    expect(collectTrackTags(model)).toEqual([])
  })
})

describe('deriveTrackTagMatches', () => {
  const model = roadmap([
    section('s1', [
      subsection('a', ['frontend', 'beginner']),
      subsection('b', ['backend', 'beginner']),
    ]),
    section('s2', [subsection('c', ['frontend', 'advanced'])]),
  ])

  it('returns all valid subsections and a null match set when no tags are selected', () => {
    const result = deriveTrackTagMatches(model, new Set(), 'all')

    expect(result.availableTags).toEqual(['frontend', 'beginner', 'backend', 'advanced'])
    expect(result.matchingSubsectionIds).toBeNull()
    expect(result.shownTopicCount).toBe(3)
    expect(result.totalTopicCount).toBe(3)
  })

  it('returns the union of matching topics in ANY mode', () => {
    const result = deriveTrackTagMatches(model, new Set(['frontend', 'backend']), 'any')

    expect([...result.matchingSubsectionIds ?? []]).toEqual(['a', 'b', 'c'])
    expect(result.shownTopicCount).toBe(3)
  })

  it('returns the intersection of matching topics in ALL mode', () => {
    const result = deriveTrackTagMatches(model, new Set(['frontend', 'beginner']), 'all')

    expect([...result.matchingSubsectionIds ?? []]).toEqual(['a'])
    expect(result.shownTopicCount).toBe(1)
  })

  it('returns zero matches when no topic contains every selected tag', () => {
    const result = deriveTrackTagMatches(model, new Set(['backend', 'advanced']), 'all')

    expect(result.matchingSubsectionIds).toEqual(new Set())
    expect(result.shownTopicCount).toBe(0)
    expect(result.totalTopicCount).toBe(3)
  })

  it('ignores malformed structural references consistently', () => {
    const malformed = roadmap([section('s1', [subsection('a', ['frontend'])])], ['missing', 's1'])
    const malformedSection = malformed.sections?.s1
    if (!malformedSection) throw new Error('expected test section')
    malformedSection.subsection_order = ['missing-subsection', 'a']

    const result = deriveTrackTagMatches(malformed, new Set(['frontend']), 'any')

    expect(result.availableTags).toEqual(['frontend'])
    expect([...result.matchingSubsectionIds ?? []]).toEqual(['a'])
    expect(result.shownTopicCount).toBe(1)
    expect(result.totalTopicCount).toBe(1)
  })
})
