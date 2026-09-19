import { describe, expect, it } from 'vitest'

import type { AgentSession } from '../types'
import {
  assertBoundedRemap,
  authoringScopes,
  buildAuthoringRoadmap,
  buildReplacementRoadmap,
  createAuthoringContext,
  resolveRoadmapIds,
  runAuthoringJourney,
} from './authoring-journey'
const identity = {
  title: 'Attempt roadmap',
  proposedIdPrefix: 'attempt',
  itemIds: ['attempt_read', 'attempt_drill', 'attempt_hash'],
}

function roadmapOutput(overrides: {
  id: string
  title: string
  description: string | null
  status: string
  revision: number
  sectionId: string
  subsectionIds: readonly string[]
  itemIds: readonly string[]
}): Record<string, unknown> {
  const [arraysId, hashingId] = overrides.subsectionIds
  const [readId, drillId, hashId] = overrides.itemIds
  const arraysResourceId = `${arraysId}-resource`
  const hashingResourceId = `${hashingId}-resource`
  return {
    created_at: '2026-01-01T00:00:00Z',
    description: overrides.description,
    id: overrides.id,
    owner: 'attempt-owner',
    published_visibility: 'public',
    revision: overrides.revision,
    section_order: [overrides.sectionId],
    sections: {
      [overrides.sectionId]: {
        id: overrides.sectionId,
        subsection_order: [arraysId, hashingId],
        subsections: {
          [arraysId]: {
            checklist_items: {
              [readId]: { id: readId, text: 'Read' },
              [drillId]: { id: drillId, text: 'Drill' },
            },
            description: null,
            effort_estimate: null,
            id: arraysId,
            item_order: [readId, drillId],
            prereq_ids: [],
            resource_order: [arraysResourceId],
            resources: {
              [arraysResourceId]: { id: arraysResourceId, title: 'Arrays', type: 'article', url: 'https://example.com/arrays' },
            },
            tags: ['foundations'],
            title: 'Arrays',
          },
          [hashingId]: {
            checklist_items: { [hashId]: { id: hashId, text: 'Hash' } },
            description: null,
            effort_estimate: null,
            id: hashingId,
            item_order: [hashId],
            prereq_ids: [arraysId],
            resource_order: [hashingResourceId],
            resources: {
              [hashingResourceId]: { id: hashingResourceId, title: 'Hashing', type: 'video', url: 'https://example.com/hashing' },
            },
            tags: ['foundations'],
            title: 'Hashing',
          },
        },
        title: 'Foundations',
      },
    },
    status: overrides.status,
    subject_tags: ['algorithms'],
    suggested_path: [arraysId, hashingId],
    title: overrides.title,
    updated_at: '2026-01-01T00:00:00Z',
  }
}

describe('authoring journey', () => {
  it('builds a compact valid draft and replacement with stable proposed IDs', () => {
    const draft = buildAuthoringRoadmap(identity)
    const replacement = buildReplacementRoadmap(identity)

    expect(draft.sections).toHaveLength(1)
    expect(draft.sections[0].subsections.map((subsection) => subsection.proposed_id)).toEqual([
      'attempt_arrays',
      'attempt_hashing',
    ])
    expect(draft.suggested_path).toEqual(['attempt_arrays', 'attempt_hashing'])
    expect(replacement.sections[0].subsections.map((subsection) => subsection.title)).toEqual([
      'Arrays and strings',
      'Hash tables',
    ])
    expect(replacement.sections[0].subsections.map((subsection) => subsection.proposed_id)).toEqual(
      draft.sections[0].subsections.map((subsection) => subsection.proposed_id),
    )
  })

  it('rejects unknown, empty, duplicate, and oversized remaps', () => {
    const draft = buildAuthoringRoadmap(identity)
    expect(() => assertBoundedRemap({ attempt_arrays: 'sub-1' }, draft)).not.toThrow()
    expect(() => assertBoundedRemap({ unknown: 'sub-1' }, draft)).toThrow('unknown proposed ID')
    expect(() => assertBoundedRemap({ attempt_arrays: '' }, draft)).toThrow('non-empty')
    expect(() => assertBoundedRemap({ attempt_arrays: 'same', attempt_hashing: 'same' }, draft)).toThrow('unique')
    expect(() => assertBoundedRemap({
      attempt_foundations: 'a', attempt_arrays: 'b', attempt_hashing: 'c',
      attempt_arrays_guide: 'd', attempt_hashing_video: 'e', attempt_read: 'f',
      attempt_drill: 'g', attempt_hash: 'h', extra: 'i',
    }, draft)).toThrow('exceeds')
  })

  it('applies server remaps to every identity used by later writes', () => {
    expect(resolveRoadmapIds(identity, {
      attempt_foundations: 'section-1',
      attempt_arrays: 'sub-1',
      attempt_hashing: 'sub-2',
      attempt_read: 'item-1',
      attempt_drill: 'item-2',
      attempt_hash: 'item-3',
    })).toEqual({
      sectionId: 'section-1',
      subsectionIds: ['sub-1', 'sub-2'],
      itemIds: ['item-1', 'item-2', 'item-3'],
    })
  })

  it('threads returned revisions through the live authoring lifecycle and reads every write back', async () => {
    const calls: Array<{ name: string; arguments_: Record<string, unknown> }> = []
    let roadmapReadCount = 0
    const createRemap = {
      attempt_foundations: 'section-1',
      attempt_arrays: 'sub-1',
      attempt_hashing: 'sub-2',
      attempt_read: 'item-1',
      attempt_drill: 'item-2',
      attempt_hash: 'item-3',
    }
    const sourceIds = resolveRoadmapIds(identity, createRemap)
    const replacementRemap = {
      attempt_foundations: 'section-2',
      attempt_arrays: 'sub-3',
      attempt_hashing: 'sub-4',
      attempt_read: 'item-4',
      attempt_drill: 'item-5',
      attempt_hash: 'item-6',
    }
    const replacementIds = resolveRoadmapIds(identity, replacementRemap)
    const forkIds = {
      sectionId: 'fork-foundations',
      subsectionIds: ['fork-arrays', 'fork-hashing'],
      itemIds: ['fork-read', 'fork-drill', 'fork-hash'],
    }
    const agent: AgentSession = {
      authorization: {
        issuer: 'https://api.wren.test',
        clientId: 'client-id',
        clientName: 'client-name',
        grantedScopes: authoringScopes(),
        accessTokenExpiresAtEpochMs: Date.now() + 1000,
        hasRefreshToken: true,
      },
      listTools: async () => [],
      callTool: async <TOutput>(name: string, arguments_: Record<string, unknown>): Promise<TOutput> => {
        calls.push({ name, arguments_ })
        let structuredContent: Record<string, unknown>
        if (name === 'create_roadmap_draft') {
          structuredContent = { roadmap_id: 'roadmap-1', revision: 1, status: 'draft', remap: createRemap }
        } else if (name === 'patch_roadmap_draft') {
          structuredContent = {
            roadmap_id: 'roadmap-1', revision: 2,
            changed_nodes: [{ change: 'updated', id: 'sub-1', kind: 'subsection' }], remap: {},
          }
        } else if (name === 'replace_roadmap_draft') {
          structuredContent = { roadmap_id: 'roadmap-1', revision: 3, status: 'draft', remap: replacementRemap }
        } else if (name === 'validate_roadmap_draft') {
          structuredContent = { publishable: true, violations: [] }
        } else if (name === 'publish_roadmap') {
          structuredContent = { roadmap_id: 'roadmap-1', revision: 4, status: 'published' }
        } else if (name === 'edit_roadmap_metadata') {
          structuredContent = {
            roadmap_id: 'roadmap-1', title: 'Attempt roadmap Published',
            description: 'Metadata edited through the official client.', subject_tags: ['algorithms', 'authoring'],
          }
        } else if (name === 'fork_roadmap') {
          structuredContent = {
            roadmap_id: 'roadmap-2', revision: 1, status: 'draft', source_roadmap_id: 'roadmap-1',
          }
        } else if (name === 'progress_get') {
          structuredContent = {
            roadmap_id: 'roadmap-2', total_items: 3, checked_items: 0, percent: 0,
            deadline: null, sections: [], checked_ids: [],
          }
        } else {
          roadmapReadCount += 1
          const isFork = arguments_.roadmap_id === 'roadmap-2'
          const ids = isFork ? forkIds : roadmapReadCount >= 3 ? replacementIds : sourceIds
          const metadataRead = !isFork && roadmapReadCount === 5
          const title = metadataRead ? 'Attempt roadmap Published' : identity.title
          const description = metadataRead ? 'Metadata edited through the official client.' : 'A compact authoring journey fixture.'
          const status = isFork ? 'draft' : roadmapReadCount >= 4 ? 'published' : 'draft'
          const revision = isFork ? 1 : Math.min(roadmapReadCount, 4)
          structuredContent = roadmapOutput({
            id: isFork ? 'roadmap-2' : 'roadmap-1', title, description, status, revision,
            sectionId: ids.sectionId, subsectionIds: ids.subsectionIds, itemIds: ids.itemIds,
          })
          if (metadataRead) structuredContent.subject_tags = ['algorithms', 'authoring']
          if (roadmapReadCount === 2) {
            const source = structuredContent.sections as Record<string, Record<string, unknown>>
            const section = source[ids.sectionId]
            const subsections = section.subsections as Record<string, Record<string, unknown>>
            subsections[ids.subsectionIds[0]].title = 'Arrays and strings'
            subsections[ids.subsectionIds[0]].tags = ['foundations', 'arrays']
          }
          if (roadmapReadCount === 3) {
            const source = structuredContent.sections as Record<string, Record<string, unknown>>
            const section = source[ids.sectionId]
            const subsections = section.subsections as Record<string, Record<string, unknown>>
            subsections[ids.subsectionIds[0]].tags = ['foundations', 'arrays']
            subsections[ids.subsectionIds[1]].title = 'Hash tables'
            subsections[ids.subsectionIds[1]].tags = ['foundations', 'hashing']
            structuredContent.description = 'The replaced compact authoring fixture.'
          }
        }
        return { content: [], structuredContent } as TOutput
      },
      waitUntilCurrentAccessTokenExpires: async () => undefined,
      close: async () => undefined,
    }

    const context = createAuthoringContext(agent, {
      runId: 'run', testId: 'test', parallelIndex: 0, retry: 0, nonce: 'nonce', resourcePrefix: 'attempt',
    }, 'attempt-owner')
    const result = await runAuthoringJourney(context, identity)

    expect(result.create.remap).toEqual(createRemap)
    expect(result.replace.remap).toEqual(replacementRemap)
    expect(result.replacedRead.section_order).toEqual(['section-2'])
    expect(result.metadataRead.title).toBe('Attempt roadmap Published')
    expect(result.forkProgress.checked_items).toBe(0)
    expect(calls.map((call) => call.name)).toEqual([
      'create_roadmap_draft', 'roadmap_get', 'patch_roadmap_draft', 'roadmap_get',
      'replace_roadmap_draft', 'roadmap_get', 'validate_roadmap_draft', 'publish_roadmap',
      'roadmap_get', 'edit_roadmap_metadata', 'roadmap_get', 'fork_roadmap', 'roadmap_get', 'progress_get',
    ])
    expect(calls[2].arguments_).toMatchObject({
      roadmap_id: 'roadmap-1',
      revision: 1,
      operations: [
        { op: 'update_subsection', subsection_id: 'sub-1', title: 'Arrays and strings' },
        { op: 'set_tags', subsection_id: 'sub-1', tags: ['foundations', 'arrays'] },
      ],
    })
    expect(calls[4].arguments_).toMatchObject({
      roadmap_id: 'roadmap-1',
      full_document: {
        description: 'The replaced compact authoring fixture.',
        sections: [{ subsections: [
          { title: 'Arrays and strings', tags: ['foundations', 'arrays'] },
          { title: 'Hash tables', tags: ['foundations', 'hashing'] },
        ] }],
      },
    })
    expect(calls[4].arguments_.revision).toBeUndefined()
  })
})
