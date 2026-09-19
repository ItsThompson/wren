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
  itemIds: ['chk_attempt_read', 'chk_attempt_drill', 'chk_attempt_hash'],
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
    const calls: Array<{ name: string; arguments_: Record<string, unknown> }> = []
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
      callTool: async <TOutput>(name: string, arguments_: Record<string, unknown>): Promise<TOutput> => {
        calls.push({ name, arguments_ })
        const arraysId = 'sub_attempt_arrays'
        const hashingId = 'sub_attempt_hashing'
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
              sections: [{ section_id: 'sec_attempt_foundations', title: 'Foundations', total_items: 3, checked_items: updated ? 2 : 0, percent: updated ? 67 : 0 }],
              status: 'published',
              title: roadmap.title,
            }
          }
          if (name === 'roadmap_get_node') {
            return node(hashingId, ['chk_attempt_hash'], [{ id: arraysId, title: 'Arrays', done: updated }])
          }
          if (name === 'roadmap_get_section') {
            return { include: 'both', next_cursor: null, section_id: 'sec_attempt_foundations', steering: null, subsections: [node(arraysId, ['chk_attempt_read', 'chk_attempt_drill']), node(hashingId, ['chk_attempt_hash'], [{ id: arraysId, title: 'Arrays', done: updated }])], title: 'Foundations' }
          }
          if (name === 'roadmap_search') {
            return { hits: [{ item_id: null, kind: 'subsection', matched_tags: null, subsection_id: hashingId, title_or_text: 'Hashing' }] }
          }
          if (name === 'progress_get') {
            return { roadmap_id: roadmap.roadmapId, total_items: 3, checked_items: updated ? 2 : 0, percent: updated ? 67 : 0, deadline: null, sections: [], checked_ids: updated ? ['chk_attempt_drill', 'chk_attempt_read'] : [] }
          }
          if (name === 'roadmap_get_next') {
            return updated
              ? { complete: false, items: [{ item_id: 'chk_attempt_hash', path_position: 2, resources: [], subsection_id: hashingId, text: 'chk_attempt_hash', why_now: 'Prerequisites are complete' }], remaining_in_path: 1 }
              : { complete: false, items: [{ item_id: 'chk_attempt_read', path_position: 0, resources: [], subsection_id: arraysId, text: 'chk_attempt_read', why_now: 'First item' }, { item_id: 'chk_attempt_drill', path_position: 0, resources: [], subsection_id: arraysId, text: 'chk_attempt_drill', why_now: 'First item' }], remaining_in_path: 2 }
          }
          if (name === 'progress_update') {
            updated = true
            return {
              progress: { roadmap_id: roadmap.roadmapId, total_items: 3, checked_items: 2, percent: 67, deadline: null, sections: [], checked_ids: ['chk_attempt_drill', 'chk_attempt_read'] },
              next: { complete: false, items: [{ item_id: 'chk_attempt_hash', path_position: 2, resources: [], subsection_id: hashingId, text: 'chk_attempt_hash', why_now: 'Prerequisites are complete' }], remaining_in_path: 1 },
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
    expect(result.finalProgress.checked_ids).toEqual(['chk_attempt_drill', 'chk_attempt_read'])
    expect(result.initialNext.items.map((item) => item.item_id)).toEqual(['chk_attempt_read', 'chk_attempt_drill'])
    expect(result.finalNext.items.map((item) => item.item_id)).toEqual(['chk_attempt_hash'])
    expect(calls).toEqual([
      { name: 'roadmap_list', arguments_: {} },
      { name: 'roadmap_get_profile', arguments_: { handle: roadmap.ownerHandle } },
      { name: 'roadmap_get_overview', arguments_: { roadmap_id: roadmap.roadmapId } },
      {
        name: 'roadmap_get_node',
        arguments_: { roadmap_id: roadmap.roadmapId, subsection_id: 'sub_attempt_hashing', format: 'detailed' },
      },
      {
        name: 'roadmap_get_section',
        arguments_: { roadmap_id: roadmap.roadmapId, section_id: 'sec_attempt_foundations', include: 'both' },
      },
      { name: 'roadmap_search', arguments_: { roadmap_id: roadmap.roadmapId, query: 'hash' } },
      { name: 'progress_get', arguments_: { roadmap_id: roadmap.roadmapId, detailed: true } },
      { name: 'roadmap_get_next', arguments_: { roadmap_id: roadmap.roadmapId, format: 'detailed' } },
      {
        name: 'progress_update',
        arguments_: { roadmap_id: roadmap.roadmapId, item_ids: ['chk_attempt_read', 'chk_attempt_drill'], state: 'complete' },
      },
      { name: 'progress_get', arguments_: { roadmap_id: roadmap.roadmapId, detailed: true } },
      { name: 'roadmap_get_next', arguments_: { roadmap_id: roadmap.roadmapId, format: 'detailed' } },
    ])
  })
})
