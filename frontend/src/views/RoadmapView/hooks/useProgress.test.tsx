import { act, renderHook, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll } from 'vitest'

import type { components } from '@/api'
import { createHookWrapper } from '@/test/createHookWrapper'
import { TEST_API_BASE } from '@/test/test-api-base'

import type { NextResult, ProgressSnapshot, ProgressUpdateResult } from '../types'
import { useProgress } from './useProgress'

const ROADMAP_ID = 'grokking-dsa-7f3k'
const PROGRESS_URL = `${TEST_API_BASE}/roadmaps/${ROADMAP_ID}/progress`
const NEXT_URL = `${TEST_API_BASE}/roadmaps/${ROADMAP_ID}/next`
const DEADLINE_URL = `${TEST_API_BASE}/roadmaps/${ROADMAP_ID}/deadline`

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

/** A minimal detailed `ProgressSnapshot` in the generated shape; override per test. */
function buildSnapshot(overrides: Partial<ProgressSnapshot> = {}): ProgressSnapshot {
  return { roadmap_id: ROADMAP_ID, total_items: 4, checked_items: 0, percent: 0, checked_ids: [], ...overrides }
}

/** A `GET /next` body; defaults to "nothing next / not complete". */
function buildNext(overrides: Partial<NextResult> = {}): NextResult {
  return { items: [], remaining_in_path: 0, complete: false, ...overrides }
}

/** A `NextResult` whose first item points at `subsectionId` (the highlight). */
function nextAt(subsectionId: string): NextResult {
  return buildNext({
    items: [{ subsection_id: subsectionId, item_id: `${subsectionId}_item`, text: 't', why_now: 'w' }],
    remaining_in_path: 1,
  })
}

/** The `POST /progress` body: fresh snapshot + reconciled next suggestion. */
function buildUpdateResult(snapshot: ProgressSnapshot, next: NextResult): ProgressUpdateResult {
  return { progress: snapshot, next }
}

/** The `Progress` record the `PUT /deadline` endpoint echoes back. */
function buildProgressRecord(deadline: string | null): components['schemas']['Progress'] {
  return { user_id: 'user-1', roadmap_id: ROADMAP_ID, deadline, checked: {}, updated_at: '2026-07-15T00:00:00Z' }
}

/** A 409 problem+json body carrying the STALE_REVISION code (the re-read branch). */
function staleConflict() {
  return HttpResponse.json(
    { type: 'x', title: 'Conflict', status: 409, code: 'STALE_REVISION', detail: 're-read' },
    { status: 409, headers: { 'content-type': 'application/problem+json' } },
  )
}

/** Install the two mount reads (progress + next) with the given seed. */
function seedReads(snapshot: ProgressSnapshot, next: NextResult = buildNext()): void {
  server.use(
    http.get(PROGRESS_URL, () => HttpResponse.json(snapshot)),
    http.get(NEXT_URL, () => HttpResponse.json(next)),
  )
}

/** Mount `useProgress` under the production-parity provider stack. */
function renderProgress() {
  return renderHook(() => useProgress(ROADMAP_ID), { wrapper: createHookWrapper() })
}

describe('useProgress reads', () => {
  it('seeds checkedIds, deadline, and the next highlight from the two reads', async () => {
    seedReads(buildSnapshot({ checked_ids: ['a', 'b'], deadline: '2099-12-31' }), nextAt('sub_hashing'))
    const { result } = renderProgress()

    await waitFor(() => expect([...result.current.checkedIds].sort()).toEqual(['a', 'b']))
    expect(result.current.deadline).toBe('2099-12-31')
    expect(result.current.nextSubsectionId).toBe('sub_hashing')
    expect(result.current.nextComplete).toBe(false)
    expect(result.current.notice).toBeNull()
  })
})

describe('useProgress toggle', () => {
  it('optimistically checks an item and reconciles BOTH keys from the write response', async () => {
    seedReads(buildSnapshot({ checked_ids: ['a'] }), buildNext())
    let posted: unknown
    server.use(
      http.post(PROGRESS_URL, async ({ request }) => {
        posted = await request.json()
        // The write both extends the checked set and completes the path: proves the
        // progress key AND the next key reconcile from the single response.
        return HttpResponse.json(buildUpdateResult(buildSnapshot({ checked_ids: ['a', 'b'] }), buildNext({ complete: true })))
      }),
    )
    const { result } = renderProgress()
    await waitFor(() => expect([...result.current.checkedIds]).toEqual(['a']))

    act(() => result.current.toggle('b', true))
    // Optimistic: the checkbox reflects instantly, before the write resolves.
    expect(result.current.checkedIds.has('b')).toBe(true)

    await waitFor(() => expect([...result.current.checkedIds].sort()).toEqual(['a', 'b']))
    // The next key reconciled from the same POST body (not a re-fetch).
    expect(result.current.nextComplete).toBe(true)
    expect(result.current.nextSubsectionId).toBeNull()
    // Explicit-set complete for exactly the toggled item (matched by URL + method).
    expect(posted).toEqual({ item_ids: ['b'], state: 'complete' })
  })

  it('sends state=incomplete and optimistically clears the item when unchecking', async () => {
    seedReads(buildSnapshot({ checked_ids: ['a', 'b'] }), buildNext())
    let posted: unknown
    server.use(
      http.post(PROGRESS_URL, async ({ request }) => {
        posted = await request.json()
        return HttpResponse.json(buildUpdateResult(buildSnapshot({ checked_ids: ['a'] }), buildNext()))
      }),
    )
    const { result } = renderProgress()
    await waitFor(() => expect([...result.current.checkedIds].sort()).toEqual(['a', 'b']))

    act(() => result.current.toggle('b', false))
    // Optimistic: the uncheck drops the item instantly.
    expect(result.current.checkedIds.has('b')).toBe(false)

    await waitFor(() => expect([...result.current.checkedIds]).toEqual(['a']))
    expect(posted).toEqual({ item_ids: ['b'], state: 'incomplete' })
  })

  it('reverts the optimistic check and surfaces a stale notice on a 409', async () => {
    seedReads(buildSnapshot({ checked_ids: ['a'] }))
    server.use(http.post(PROGRESS_URL, () => staleConflict()))
    const { result } = renderProgress()
    await waitFor(() => expect([...result.current.checkedIds]).toEqual(['a']))

    act(() => result.current.toggle('b', true))
    expect(result.current.checkedIds.has('b')).toBe(true)

    await waitFor(() => expect(result.current.notice).toEqual({ kind: 'stale' }))
    // Rolled back to the pre-toggle checked set.
    expect(result.current.checkedIds.has('b')).toBe(false)
    expect([...result.current.checkedIds]).toEqual(['a'])
  })

  it('reverts and surfaces a save-failed notice when the write throws at the network level', async () => {
    seedReads(buildSnapshot({ checked_ids: ['a'] }))
    server.use(http.post(PROGRESS_URL, () => HttpResponse.error()))
    const { result } = renderProgress()
    await waitFor(() => expect([...result.current.checkedIds]).toEqual(['a']))

    act(() => result.current.toggle('b', true))
    expect(result.current.checkedIds.has('b')).toBe(true)

    await waitFor(() => expect(result.current.notice).toEqual({ kind: 'save-failed' }))
    expect([...result.current.checkedIds]).toEqual(['a'])
  })
})

describe('useProgress setDeadline', () => {
  it('optimistically sets the deadline and folds the server value on success', async () => {
    seedReads(buildSnapshot({ deadline: null }))
    let put: unknown
    server.use(
      http.put(DEADLINE_URL, async ({ request }) => {
        put = await request.json()
        return HttpResponse.json(buildProgressRecord('2026-12-01'))
      }),
    )
    const { result } = renderProgress()
    await waitFor(() => expect(result.current.deadline).toBeNull())

    act(() => result.current.setDeadline('2026-12-01'))
    // Optimistic: the new deadline shows before the PUT resolves.
    expect(result.current.deadline).toBe('2026-12-01')

    await waitFor(() => expect(put).toEqual({ deadline: '2026-12-01' }))
    expect(result.current.deadline).toBe('2026-12-01')
  })

  it('optimistically clears the deadline and folds the null server value on success', async () => {
    seedReads(buildSnapshot({ deadline: '2099-12-31' }))
    let put: unknown
    server.use(
      http.put(DEADLINE_URL, async ({ request }) => {
        put = await request.json()
        return HttpResponse.json(buildProgressRecord(null))
      }),
    )
    const { result } = renderProgress()
    await waitFor(() => expect(result.current.deadline).toBe('2099-12-31'))

    act(() => result.current.setDeadline(null))
    // Optimistic: the deadline clears before the PUT resolves.
    expect(result.current.deadline).toBeNull()

    await waitFor(() => expect(put).toEqual({ deadline: null }))
    expect(result.current.deadline).toBeNull()
  })

  it('reverts the optimistic deadline and surfaces a notice when the PUT fails (500)', async () => {
    seedReads(buildSnapshot({ deadline: '2099-12-31' }))
    server.use(http.put(DEADLINE_URL, () => new HttpResponse(null, { status: 500 })))
    const { result } = renderProgress()
    await waitFor(() => expect(result.current.deadline).toBe('2099-12-31'))

    act(() => result.current.setDeadline('2026-12-01'))
    expect(result.current.deadline).toBe('2026-12-01')

    await waitFor(() => expect(result.current.notice).toEqual({ kind: 'save-failed' }))
    // Rolled back to the pre-write deadline.
    expect(result.current.deadline).toBe('2099-12-31')
  })
})

describe('useProgress dismissNotice', () => {
  it('clears a surfaced write notice', async () => {
    seedReads(buildSnapshot({ checked_ids: ['a'] }))
    server.use(http.post(PROGRESS_URL, () => new HttpResponse(null, { status: 500 })))
    const { result } = renderProgress()
    await waitFor(() => expect([...result.current.checkedIds]).toEqual(['a']))

    act(() => result.current.toggle('b', true))
    await waitFor(() => expect(result.current.notice).toEqual({ kind: 'save-failed' }))

    act(() => result.current.dismissNotice())
    expect(result.current.notice).toBeNull()
  })
})

describe('useProgress reload', () => {
  it('clears any notice and refetches both reads', async () => {
    let snapshot = buildSnapshot({ checked_ids: ['a'] })
    let next = buildNext()
    let progressGets = 0
    let nextGets = 0
    server.use(
      http.get(PROGRESS_URL, () => {
        progressGets += 1
        return HttpResponse.json(snapshot)
      }),
      http.get(NEXT_URL, () => {
        nextGets += 1
        return HttpResponse.json(next)
      }),
      http.post(PROGRESS_URL, () => new HttpResponse(null, { status: 500 })),
    )
    const { result } = renderProgress()
    await waitFor(() => expect([...result.current.checkedIds]).toEqual(['a']))
    const progressGetsBeforeReload = progressGets
    const nextGetsBeforeReload = nextGets

    // Surface a notice, then let the server return a fresh checked set + highlight.
    act(() => result.current.toggle('b', true))
    await waitFor(() => expect(result.current.notice).toEqual({ kind: 'save-failed' }))
    snapshot = buildSnapshot({ checked_ids: ['a', 'x'] })
    next = nextAt('sub_new')

    act(() => result.current.reload())

    await waitFor(() => {
      expect(result.current.notice).toBeNull()
      expect([...result.current.checkedIds].sort()).toEqual(['a', 'x'])
      expect(result.current.nextSubsectionId).toBe('sub_new')
    })
    expect(progressGets).toBeGreaterThan(progressGetsBeforeReload)
    expect(nextGets).toBeGreaterThan(nextGetsBeforeReload)
  })
})
