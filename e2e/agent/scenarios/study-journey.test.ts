import { describe, expect, it } from 'vitest'

import type { AgentSession } from '../types'
import {
  createStudyContext,
  runStudyJourney,
  studyScopes,
  type StudyRoadmapIdentity,
} from './study-journey'

const roadmap: StudyRoadmapIdentity = {
  title: 'Attempt study roadmap',
  proposedIdPrefix: 'attempt',
  itemIds: ['attempt_read', 'attempt_drill', 'attempt_hash'],
  roadmapId: 'roadmap-1',
  ownerHandle: 'attempt-owner',
}

function node(subsectionId: string, itemIds: readonly string[], prereqs: readonly object[] = []) {
  return {
    description: null,
    effort_estimate: null,
    items: itemIds.map((id) => ({ id, text: id, done: false })),
    prereqs,
    resources: [{ id: `${subsectionId}-resource`, title: 'Guide', type: 'article', url: 'https://example.com/guide' }],
    subsection_id: subsectionId,
    tags: ['foundations'],
    title: subsectionId,
  }
}

describe('study journey', () => {
  it('reads the published study surface and observes progress advancement', async () => {
    const calls: string[] = []
    let updated = false
    const agent: AgentSession = {
      authorization: {
        issuer: 'https://api.wren.test',
        clientId: 'client-id',
        clientName: 'client-name',
        grantedScopes: studyScopes(),
        accessTokenExpiresAtEpochMs: Date.now() + 1000,
        hasRefreshToken: true,
      },
      listTools: async () => [],
      callTool: async <TOutput>(name: string): Promise<TOutput> => {
        calls.push(name)
        const arraysId = 'attempt_arrays'
        const hashingId = 'attempt_hashing'
        const content = (() => {
          if (name === 'roadmap_list') {
            return { authored: [{ id: roadmap.roadmapId, published_visibility: 'public', status: 'published', subject_tags: [], title: roadmap.title }], followed: [] }
          }
          if (name === 'roadmap_get_profile') {
            return { display_name: 'Attempt Owner', handle: roadmap.ownerHandle, roadmaps: [{ id: roadmap.roadmapId, published_visibility: 'public', status: 'published', subject_tags: [], title: roadmap.title }] }
          }
          if (name === 'roadmap_get_overview') {
            return {
              details: null,
              overall: { total_items: 3, checked_items: updated ? 2 : 0, percent: updated ? 67 : 0 },
              revision: 1,
              roadmap_id: roadmap.roadmapId,
              sections: [{ section_id: 'attempt_foundations', title: 'Foundations', total_items: 3, checked_items: updated ? 2 : 0, percent: updated ? 67 : 0 }],
              status: 'published',
              title: roadmap.title,
            }
          }
          if (name === 'roadmap_get_node') {
            return node(hashingId, ['attempt_hash'], [{ id: arraysId, title: 'Arrays', done: updated }])
          }
          if (name === 'roadmap_get_section') {
            return { include: 'both', next_cursor: null, section_id: 'attempt_foundations', steering: null, subsections: [node(arraysId, ['attempt_read', 'attempt_drill']), node(hashingId, ['attempt_hash'], [{ id: arraysId, title: 'Arrays', done: updated }])], title: 'Foundations' }
          }
          if (name === 'roadmap_search') {
            return { hits: [{ item_id: null, kind: 'subsection', matched_tags: null, subsection_id: hashingId, title_or_text: 'Hashing' }] }
          }
          if (name === 'progress_get') {
            return { roadmap_id: roadmap.roadmapId, total_items: 3, checked_items: updated ? 2 : 0, percent: updated ? 67 : 0, deadline: null, sections: [], checked_ids: updated ? ['attempt_drill', 'attempt_read'] : [] }
          }
          if (name === 'roadmap_get_next') {
            return updated
              ? { complete: false, items: [{ item_id: 'attempt_hash', path_position: 2, resources: [], subsection_id: hashingId, text: 'attempt_hash', why_now: 'Prerequisites are complete' }], remaining_in_path: 1 }
              : { complete: false, items: [{ item_id: 'attempt_read', path_position: 0, resources: [], subsection_id: arraysId, text: 'attempt_read', why_now: 'First item' }, { item_id: 'attempt_drill', path_position: 0, resources: [], subsection_id: arraysId, text: 'attempt_drill', why_now: 'First item' }], remaining_in_path: 2 }
          }
          if (name === 'progress_update') {
            updated = true
            return {
              progress: { roadmap_id: roadmap.roadmapId, total_items: 3, checked_items: 2, percent: 67, deadline: null, sections: [], checked_ids: ['attempt_drill', 'attempt_read'] },
              next: { complete: false, items: [{ item_id: 'attempt_hash', path_position: 2, resources: [], subsection_id: hashingId, text: 'attempt_hash', why_now: 'Prerequisites are complete' }], remaining_in_path: 1 },
            }
          }
          throw new Error(`unexpected tool ${name}`)
        })()
        return { content: [], structuredContent: content } as TOutput
      },
      waitUntilCurrentAccessTokenExpires: async () => undefined,
      close: async () => undefined,
    }

    const context = createStudyContext(agent, {
      runId: 'run', testId: 'test', parallelIndex: 0, retry: 0, nonce: 'nonce', resourcePrefix: 'attempt',
    }, roadmap)
    const result = await runStudyJourney(context, roadmap)

    expect(result.initialProgress.checked_items).toBe(0)
    expect(result.finalProgress.checked_ids).toEqual(['attempt_drill', 'attempt_read'])
    expect(result.initialNext.items.map((item) => item.item_id)).toEqual(['attempt_read', 'attempt_drill'])
    expect(result.finalNext.items.map((item) => item.item_id)).toEqual(['attempt_hash'])
    expect(calls).toEqual([
      'roadmap_list', 'roadmap_get_profile', 'roadmap_get_overview', 'roadmap_get_node',
      'roadmap_get_section', 'roadmap_search', 'progress_get', 'roadmap_get_next',
      'progress_update', 'progress_get', 'roadmap_get_next',
    ])
  })
})
