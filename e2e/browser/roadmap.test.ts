import { describe, expect, it } from 'vitest'

import { createAgentStudyJourneyState } from './roadmap'
import type { RoadmapOutput } from '../agent/scenarios/types'

function buildRoadmap(): RoadmapOutput {
  return {
    created_at: '2026-01-01T00:00:00Z',
    description: 'Study fixture',
    id: 'roadmap-server-id',
    owner: 'owner',
    published_visibility: 'public',
    revision: 3,
    section_order: ['section-server-id'],
    sections: {
      'section-server-id': {
        id: 'section-server-id',
        title: 'Foundations',
        subsection_order: ['first-server-id', 'second-server-id'],
        subsections: {
          'first-server-id': {
            checklist_items: {
              'first-item-server-id': { id: 'first-item-server-id', text: 'First item' },
              'second-item-server-id': { id: 'second-item-server-id', text: 'Second item' },
            },
            description: null,
            effort_estimate: null,
            id: 'first-server-id',
            item_order: ['first-item-server-id', 'second-item-server-id'],
            prereq_ids: [],
            resource_order: [],
            resources: {},
            tags: [],
            title: 'First topic',
          },
          'second-server-id': {
            checklist_items: {
              'final-item-server-id': { id: 'final-item-server-id', text: 'Final item' },
            },
            description: null,
            effort_estimate: null,
            id: 'second-server-id',
            item_order: ['final-item-server-id'],
            prereq_ids: ['first-server-id'],
            resource_order: [],
            resources: {},
            tags: [],
            title: 'Second topic',
          },
        },
      },
    },
    status: 'published',
    subject_tags: [],
    suggested_path: ['first-server-id', 'second-server-id'],
    title: 'Agent roadmap',
    updated_at: '2026-01-01T00:00:00Z',
  }
}

describe('createAgentStudyJourneyState', () => {
  it('carries server identities and labels from the official roadmap response', () => {
    const state = createAgentStudyJourneyState(
      buildRoadmap(),
      {
        subsectionIds: ['first-server-id', 'second-server-id'],
        itemIds: ['first-item-server-id', 'second-item-server-id', 'final-item-server-id'],
      },
      '2099-12-31',
    )

    expect(state).toEqual({
      roadmapId: 'roadmap-server-id',
      title: 'Agent roadmap',
      firstSubsectionId: 'first-server-id',
      firstSubsectionTitle: 'First topic',
      secondSubsectionId: 'second-server-id',
      secondSubsectionTitle: 'Second topic',
      prerequisiteItems: [
        { id: 'first-item-server-id', text: 'First item' },
        { id: 'second-item-server-id', text: 'Second item' },
      ],
      finalItem: { id: 'final-item-server-id', text: 'Final item' },
      deadlineIso: '2099-12-31',
    })
  })

  it('rejects incomplete official journey state before browser interaction', () => {
    expect(() =>
      createAgentStudyJourneyState(
        buildRoadmap(),
        { subsectionIds: ['first-server-id'], itemIds: ['first-item-server-id'] },
        '2099-12-31',
      ),
    ).toThrow('two subsections and three checklist items')
  })
})
