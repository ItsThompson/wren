import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse, delay } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'

import { mockAuthUser, mockNext, mockProgress, mockRoadmap } from '@/mocks/data'
import { renderWithProviders } from '@/test/renderWithProviders'
import { useProgress } from '@/views/RoadmapView/hooks/useProgress'
import { useRoadmap } from '@/views/RoadmapView/hooks/useRoadmap'

/**
 * Single-refresh lock. `useRoadmap` and `useProgress` co-mounted read
 * through the ONE shared session client built by `ApiClientProvider`. When their
 * reads all 401 concurrently, the client's `refreshOnce` in-flight-promise
 * coalesces them into a single `POST /auth/refresh`, and every original request
 * retries after the refresh succeeds. This is the guarantee the centralized
 * provider unlocked: before it, each hook built its own client with its own
 * refresh lock, so N co-mounted 401s could fire up to N refreshes.
 *
 * The controlled (non-real) auth mode is used deliberately: it does NOT mount
 * `AuthProvider`, so the ONLY `POST /auth/refresh` the counter can see is the one
 * issued by the 401-retry middleware, not a mount-time session resume.
 */

const BASE = 'https://api.test'
const ROADMAP_ID = mockRoadmap.id

/** Co-mounts the two reads on the shared session client (useProgress issues two). */
function ConcurrentReadsProbe() {
  const roadmap = useRoadmap(ROADMAP_ID)
  const progress = useProgress(ROADMAP_ID)
  return (
    <div>
      <span data-testid="roadmap-phase">{roadmap.state.phase}</span>
      <span data-testid="checked">{progress.checkedIds.size}</span>
      <span data-testid="next">{progress.nextSubsectionId ?? 'none'}</span>
    </div>
  )
}

const server = setupServer()

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

describe('AC4 single-refresh lock: concurrent 401s coalesce to one refresh', () => {
  it('issues exactly one POST /auth/refresh for concurrent 401s and retries every original read', async () => {
    let refreshCalls = 0
    let roadmapGets = 0
    let progressGets = 0
    let nextGets = 0

    server.use(
      // A slow refresh keeps its promise pending while all three initial 401s are
      // handled, so they deterministically coalesce onto the one in-flight refresh.
      http.post('*/auth/refresh', async () => {
        refreshCalls += 1
        await delay(20)
        return HttpResponse.json(mockAuthUser)
      }),
      // Each read: 401 on the first hit (expired session), 200 on the retry that
      // the middleware replays after the shared refresh rotates the cookie.
      http.get('*/roadmaps/:id/progress', () => {
        progressGets += 1
        return progressGets === 1
          ? new HttpResponse(null, { status: 401 })
          : HttpResponse.json(mockProgress)
      }),
      http.get('*/roadmaps/:id/next', () => {
        nextGets += 1
        return nextGets === 1
          ? new HttpResponse(null, { status: 401 })
          : HttpResponse.json(mockNext)
      }),
      http.get('*/roadmaps/:id', () => {
        roadmapGets += 1
        return roadmapGets === 1
          ? new HttpResponse(null, { status: 401 })
          : HttpResponse.json(mockRoadmap)
      }),
    )

    renderWithProviders(<ConcurrentReadsProbe />, { baseUrl: BASE })

    // The roadmap read retried and resolved.
    await waitFor(() => expect(screen.getByTestId('roadmap-phase')).toHaveTextContent('loaded'))
    // The progress + next reads retried and resolved (checked set + next item present).
    await waitFor(() =>
      expect(screen.getByTestId('checked')).toHaveTextContent(
        String(mockProgress.checked_ids?.length ?? 0),
      ),
    )

    // Exactly one refresh coalesced all concurrent 401s.
    expect(refreshCalls).toBe(1)
    // Every original request retried once (401 then 200), proving transparent recovery.
    expect(roadmapGets).toBe(2)
    expect(progressGets).toBe(2)
    expect(nextGets).toBe(2)
  })
})
