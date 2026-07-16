import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest'

import { mockRoadmap } from '@/mocks/data'
import { renderWithProviders } from '@/test/renderWithProviders'
import type { Roadmap } from '@/views/RoadmapView/types'
import { useRoadmap } from '@/views/RoadmapView/hooks/useRoadmap'

/**
 * AC5 (revalidate-after-write). Every write that returns the updated resource
 * (publish / editMetadata / visibility / archive) reconciles the read cache in
 * place via `mutate(returned, { revalidate: false })`, so the view reflects the
 * new server state with NO stale flash (the phase never returns to `loading`
 * after the first load) and NO unnecessary extra GET (the mount read is the only
 * `GET /roadmaps/{id}`).
 *
 * The revoke case (`DELETE /me/clients/{id}` with no follow-up GET) is asserted
 * in `ConnectedClientsView.test.tsx`; the optimistic progress writes (no extra
 * GET via `revalidate: false`) are asserted in `RoadmapView.test.tsx`.
 */

const BASE = 'https://api.test'
const ROADMAP_ID = mockRoadmap.id
// Colon-action endpoints are matched by concrete URL (path-to-regexp treats a
// second `:` in `:id:publish` as another param), mirroring RoadmapView.test.tsx.
const PUBLISH_URL = `${BASE}/roadmaps/${ROADMAP_ID}:publish`
const ARCHIVE_URL = `${BASE}/roadmaps/${ROADMAP_ID}:archive`
const METADATA_URL = `${BASE}/roadmaps/${ROADMAP_ID}/metadata`
const VISIBILITY_URL = `${BASE}/roadmaps/${ROADMAP_ID}/visibility`

/** Phases observed across every render, to detect a stale flash (a loading relapse). */
const phases: string[] = []

function draft(overrides: Partial<Roadmap> = {}): Roadmap {
  return { ...mockRoadmap, status: 'draft', visibility: 'private', ...overrides }
}
function published(overrides: Partial<Roadmap> = {}): Roadmap {
  return { ...mockRoadmap, status: 'published', visibility: 'public', ...overrides }
}

/** Reads one roadmap and exposes each write action as a button. */
function WriteProbe() {
  const { state, publish, editMetadata, lifecycle } = useRoadmap(ROADMAP_ID)
  phases.push(state.phase)
  return (
    <div>
      <span data-testid="phase">{state.phase}</span>
      <span data-testid="title">{state.phase === 'loaded' ? state.roadmap.title : ''}</span>
      <span data-testid="status">{state.phase === 'loaded' ? state.roadmap.status : ''}</span>
      <span data-testid="visibility">{state.phase === 'loaded' ? state.roadmap.visibility : ''}</span>
      <button type="button" onClick={() => void publish()}>
        publish
      </button>
      <button
        type="button"
        onClick={() =>
          void editMetadata({ title: 'Renamed live', description: 'd', subject_tags: ['x'] })
        }
      >
        edit
      </button>
      <button type="button" onClick={() => lifecycle.setVisibility('private')}>
        make-private
      </button>
      <button type="button" onClick={() => lifecycle.archive()}>
        archive
      </button>
    </div>
  )
}

const server = setupServer()

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
beforeEach(() => {
  phases.length = 0
})
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

/** True once the read has loaded and never relapsed to `loading` (no stale flash). */
function noStaleFlash(): boolean {
  const firstLoaded = phases.indexOf('loaded')
  return firstLoaded !== -1 && phases.slice(firstLoaded).every((phase) => phase === 'loaded')
}

describe('AC5 revalidate-after-write: server state reflected with no stale flash and no extra GET', () => {
  it('publish reflects the returned published roadmap in place', async () => {
    const user = userEvent.setup()
    let roadmapGets = 0
    server.use(
      http.get('*/roadmaps/:id', () => {
        roadmapGets += 1
        return HttpResponse.json(draft())
      }),
      http.post(PUBLISH_URL, () => HttpResponse.json(published())),
    )
    renderWithProviders(<WriteProbe />, { baseUrl: BASE })
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('draft'))

    await user.click(screen.getByRole('button', { name: 'publish' }))

    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('published'))
    expect(roadmapGets).toBe(1) // no revalidating GET after the write
    expect(noStaleFlash()).toBe(true)
  })

  it('editMetadata reflects the returned title in place', async () => {
    const user = userEvent.setup()
    let roadmapGets = 0
    server.use(
      http.get('*/roadmaps/:id', () => {
        roadmapGets += 1
        return HttpResponse.json(published())
      }),
      http.patch(METADATA_URL, () => HttpResponse.json(published({ title: 'Renamed live' }))),
    )
    renderWithProviders(<WriteProbe />, { baseUrl: BASE })
    await waitFor(() => expect(screen.getByTestId('title')).toHaveTextContent(mockRoadmap.title))

    await user.click(screen.getByRole('button', { name: 'edit' }))

    await waitFor(() => expect(screen.getByTestId('title')).toHaveTextContent('Renamed live'))
    expect(roadmapGets).toBe(1)
    expect(noStaleFlash()).toBe(true)
  })

  it('visibility toggle reflects the returned visibility in place', async () => {
    const user = userEvent.setup()
    let roadmapGets = 0
    server.use(
      http.get('*/roadmaps/:id', () => {
        roadmapGets += 1
        return HttpResponse.json(published())
      }),
      http.put(VISIBILITY_URL, () => HttpResponse.json(published({ visibility: 'private' }))),
    )
    renderWithProviders(<WriteProbe />, { baseUrl: BASE })
    await waitFor(() => expect(screen.getByTestId('visibility')).toHaveTextContent('public'))

    await user.click(screen.getByRole('button', { name: 'make-private' }))

    await waitFor(() => expect(screen.getByTestId('visibility')).toHaveTextContent('private'))
    expect(roadmapGets).toBe(1)
    expect(noStaleFlash()).toBe(true)
  })

  it('archive reflects the returned archived status in place', async () => {
    const user = userEvent.setup()
    let roadmapGets = 0
    server.use(
      http.get('*/roadmaps/:id', () => {
        roadmapGets += 1
        return HttpResponse.json(published())
      }),
      http.post(ARCHIVE_URL, () => HttpResponse.json(published({ status: 'archived' }))),
    )
    renderWithProviders(<WriteProbe />, { baseUrl: BASE })
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('published'))

    await user.click(screen.getByRole('button', { name: 'archive' }))

    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('archived'))
    expect(roadmapGets).toBe(1)
    expect(noStaleFlash()).toBe(true)
  })
})
