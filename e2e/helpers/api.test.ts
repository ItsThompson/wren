import { describe, expect, it } from 'vitest'

import { createAttemptIdentity, createRoadmapIdentity } from '../fixtures/attempt-identity.ts'
import { buildPublishableRoadmap } from './api.ts'

describe('API fixture payloads', () => {
  it('uses the attempt roadmap identity for every proposed roadmap identifier', () => {
    const attemptIdentity = createAttemptIdentity({
      runId: 'run-123',
      projectName: 'chromium',
      file: 'roadmap.spec.ts',
      title: 'creates a roadmap',
      parallelIndex: 1,
      retry: 0,
      nonce: 'fixed123',
    })
    const roadmapIdentity = createRoadmapIdentity(attemptIdentity)
    const roadmap = buildPublishableRoadmap({ identity: roadmapIdentity })
    const section = roadmap.sections[0]
    const subsections = section.subsections

    expect(roadmap.title).toBe(roadmapIdentity.title)
    expect(roadmap.suggested_path).toEqual([
      `sub_${roadmapIdentity.proposedIdPrefix}-arrays`,
      `sub_${roadmapIdentity.proposedIdPrefix}-hashing`,
    ])
    expect(subsections[0].proposed_id).toBe(`sub_${roadmapIdentity.proposedIdPrefix}-arrays`)
    expect(subsections[0].checklist_items.map((item) => item.proposed_id)).toEqual(
      roadmapIdentity.itemIds.slice(0, 2),
    )
    expect(subsections[1].proposed_id).toBe(`sub_${roadmapIdentity.proposedIdPrefix}-hashing`)
    expect(subsections[1].checklist_items[0].proposed_id).toBe(roadmapIdentity.itemIds[2])
  })
})
