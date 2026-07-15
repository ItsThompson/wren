import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'

import { AuthProvider } from '@/auth'
import type { RoadmapCardData } from './types'
import { DashboardView } from './DashboardView'

const BASE = 'https://api.test'

const AUTH_USER = {
  id: 'user-1',
  username: 'ada',
  email: 'ada@example.com',
  created_at: '2026-07-15T00:00:00Z',
}

const authedRefresh = () => http.post('*/auth/refresh', () => HttpResponse.json(AUTH_USER))
const anonRefresh = () => http.post('*/auth/refresh', () => new HttpResponse(null, { status: 401 }))

function buildCard(overrides: Partial<RoadmapCardData> = {}): RoadmapCardData {
  return {
    id: 'grokking-dsa-7f3k',
    title: 'Grokking DSA',
    status: 'published',
    visibility: 'public',
    subject_tags: ['cs'],
    ...overrides,
  }
}

const server = setupServer()

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

function renderView() {
  return render(
    <AuthProvider baseUrl={BASE}>
      <MemoryRouter initialEntries={['/dashboard']}>
        <Routes>
          <Route path="/dashboard" element={<DashboardView baseUrl={BASE} />} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  )
}

describe('DashboardView', () => {
  it('renders the Yours and Following sections with status + visibility badges', async () => {
    server.use(
      authedRefresh(),
      http.get('*/me/dashboard', () =>
        HttpResponse.json({
          authored: [
            buildCard({ id: 'r-draft', title: 'Systems Design', status: 'draft', visibility: 'private', subject_tags: ['systems'] }),
            buildCard({ id: 'r-pub', title: 'Grokking DSA', status: 'published', visibility: 'public' }),
          ],
          followed: [
            buildCard({ id: 'r-follow', title: 'Rust in Practice', status: 'published', visibility: 'public' }),
          ],
        }),
      ),
    )
    renderView()
    expect(screen.getByLabelText('Loading your dashboard')).toBeInTheDocument()

    expect(await screen.findByRole('heading', { name: 'Yours' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Following' })).toBeInTheDocument()

    // Authored (any status) and followed roadmaps both render as cards.
    expect(screen.getByText('Systems Design')).toBeInTheDocument()
    expect(screen.getByText('Rust in Practice')).toBeInTheDocument()

    // Status badges follow section 09 §7.9 (label carries meaning, not color alone).
    expect(screen.getByText('Draft')).toBeInTheDocument()
    expect(screen.getAllByText('Published').length).toBe(2)
    expect(screen.getByText('Private')).toBeInTheDocument()
    expect(screen.getAllByText('Public').length).toBe(2)

    // Cards link to the roadmap view.
    expect(screen.getByRole('link', { name: /Systems Design/ })).toHaveAttribute(
      'href',
      '/roadmaps/r-draft',
    )
  })

  it('shows a per-section empty note when one list is empty', async () => {
    server.use(
      authedRefresh(),
      http.get('*/me/dashboard', () =>
        HttpResponse.json({ authored: [buildCard()], followed: [] }),
      ),
    )
    renderView()
    expect(await screen.findByRole('heading', { name: 'Yours' })).toBeInTheDocument()
    expect(screen.getByText("You aren't following any roadmaps yet.")).toBeInTheDocument()
  })

  it('shows the whole-dashboard empty state with a connect action when nothing exists', async () => {
    server.use(
      authedRefresh(),
      http.get('*/me/dashboard', () => HttpResponse.json({ authored: [], followed: [] })),
    )
    renderView()

    expect(await screen.findByText('Nothing here yet.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Connect an agent' })).toHaveAttribute(
      'href',
      '/settings/connections',
    )
    // Neither section renders in the global empty state.
    expect(screen.queryByRole('heading', { name: 'Yours' })).not.toBeInTheDocument()
  })

  it('prompts anonymous visitors to log in', async () => {
    server.use(anonRefresh())
    renderView()

    const loginLink = await screen.findByRole('link', { name: 'Log in' })
    expect(loginLink).toHaveAttribute('href', '/auth')
  })

  it('surfaces a load error with a retry that refetches', async () => {
    server.use(
      authedRefresh(),
      http.get('*/me/dashboard', () => new HttpResponse(null, { status: 500 }), { once: true }),
    )
    renderView()

    expect(await screen.findByText(/couldn’t load your dashboard/i)).toBeInTheDocument()

    server.use(http.get('*/me/dashboard', () => HttpResponse.json({ authored: [buildCard()], followed: [] })))
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Yours' })).toBeInTheDocument())
  })
})
