import { renderHook, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'

import { createHookWrapper } from '@/test/createHookWrapper'

import type { ProgressSnapshot, Roadmap } from '../types'
import { useTreeData } from './useTreeData'

const ROADMAP_ID = 'grokking-dsa-7f3k'

/** A published roadmap with a two-node prerequisite chain (Arrays -> Hashing). */
function buildRoadmap(overrides: Partial<Roadmap> = {}): Roadmap {
  return {
    id: ROADMAP_ID,
    owner: 'user-1',
    title: 'Grokking DSA',
    visibility: 'public',
    status: 'published',
    revision: 3,
    section_order: ['sec_1'],
    sections: {
      sec_1: {
        id: 'sec_1',
        title: 'Foundations',
        subsection_order: ['a', 'b'],
        subsections: {
          a: { id: 'a', title: 'Arrays', prereq_ids: [], item_order: ['a1'] },
          b: { id: 'b', title: 'Hashing', prereq_ids: ['a'], item_order: ['b1'] },
        },
      },
    },
    created_at: '2026-07-15T00:00:00Z',
    updated_at: '2026-07-15T00:00:00Z',
    ...overrides,
  }
}

function buildProgress(checkedIds: string[] = []): ProgressSnapshot {
  return {
    roadmap_id: ROADMAP_ID,
    total_items: 2,
    checked_items: checkedIds.length,
    percent: 0,
    checked_ids: checkedIds,
  }
}

const server = setupServer()

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

function renderTreeData() {
  return renderHook(() => useTreeData(ROADMAP_ID), { wrapper: createHookWrapper() })
}

describe('useTreeData', () => {
  it('resolves to loaded with the roadmap and the caller\u2019s checked set when both reads succeed', async () => {
    server.use(
      http.get('*/roadmaps/:id', () => HttpResponse.json(buildRoadmap())),
      http.get('*/roadmaps/:id/progress', () => HttpResponse.json(buildProgress(['a1']))),
    )
    const { result } = renderTreeData()

    await waitFor(() =>
      expect(result.current.state).toEqual({
        phase: 'loaded',
        roadmap: buildRoadmap(),
        checkedIds: new Set(['a1']),
      }),
    )
  })

  it('surfaces error when the fatal roadmap read fails (500)', async () => {
    server.use(
      http.get('*/roadmaps/:id', () => new HttpResponse(null, { status: 500 })),
      http.get('*/roadmaps/:id/progress', () => HttpResponse.json(buildProgress())),
    )
    const { result } = renderTreeData()

    await waitFor(() => expect(result.current.state).toEqual({ phase: 'error' }))
  })

  it('surfaces error when the roadmap read throws at the network level', async () => {
    server.use(
      http.get('*/roadmaps/:id', () => HttpResponse.error()),
      http.get('*/roadmaps/:id/progress', () => HttpResponse.json(buildProgress())),
    )
    const { result } = renderTreeData()

    await waitFor(() => expect(result.current.state).toEqual({ phase: 'error' }))
  })

  it('stays loaded with an empty checked set when the best-effort progress read fails (500)', async () => {
    server.use(
      http.get('*/roadmaps/:id', () => HttpResponse.json(buildRoadmap())),
      http.get('*/roadmaps/:id/progress', () => new HttpResponse(null, { status: 500 })),
    )
    const { result } = renderTreeData()

    await waitFor(() =>
      expect(result.current.state).toEqual({
        phase: 'loaded',
        roadmap: buildRoadmap(),
        checkedIds: new Set(),
      }),
    )
  })

  it('stays loaded with an empty checked set when the progress read throws at the network level', async () => {
    server.use(
      http.get('*/roadmaps/:id', () => HttpResponse.json(buildRoadmap())),
      http.get('*/roadmaps/:id/progress', () => HttpResponse.error()),
    )
    const { result } = renderTreeData()

    await waitFor(() =>
      expect(result.current.state).toEqual({
        phase: 'loaded',
        roadmap: buildRoadmap(),
        checkedIds: new Set(),
      }),
    )
  })
})
