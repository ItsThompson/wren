import { render, screen } from '@testing-library/react'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router'

import { AuthProvider } from '@/auth'
import { RoadmapView } from '@/views/RoadmapView'
import { handlers } from './handlers'
import { mockRoadmap } from './data'

/**
 * A runtime proof that the dev:mock fixtures render populated views: mounts the
 * real RoadmapView against the actual MSW handlers + fixtures. Before ticket 26
 * the fixtures used a pre-schema array shape, so `sections[id]` was undefined and
 * dev:mock rendered empty; this locks in that the generated-schema fixtures paint
 * real content.
 */
const BASE = 'https://api.test'
const server = setupServer(...handlers)

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

describe('dev:mock fixtures render populated views', () => {
  it('renders the published roadmap with its sections, node cards, and resources', async () => {
    render(
      <AuthProvider baseUrl={BASE}>
        <MemoryRouter initialEntries={[`/roadmaps/${mockRoadmap.id}`]}>
          <Routes>
            <Route path="/roadmaps/:roadmapId" element={<RoadmapView baseUrl={BASE} />} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>,
    )

    // The roadmap header, a section, a node card, a track tag, and a resource
    // link all render from the ID-keyed map fixtures (not empty states).
    expect(await screen.findByRole('heading', { level: 1, name: /Grokking Data Structures/ })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: 'Foundations' })).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { level: 3, name: 'Arrays & two pointers' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Two-pointer technique' })).toHaveAttribute(
      'href',
      'https://example.com/two-pointers',
    )
    // The overall progress bar renders (published tracking view, not a skeleton).
    expect(screen.getByRole('progressbar', { name: /overall progress/i })).toBeInTheDocument()
  })
})
