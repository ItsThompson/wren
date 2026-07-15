import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { Route, Routes } from 'react-router'
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'

import { renderWithProviders } from '@/test/renderWithProviders'

import { ProfileView } from './ProfileView'

const BASE = 'https://api.test'

/** RFC 9457 problem-details 404. */
function notFound(handle: string) {
  return HttpResponse.json(
    {
      type: 'https://usewren.com/errors/not-found',
      title: 'Profile not found',
      status: 404,
      code: 'NOT_FOUND',
      instance: `/users/${handle}`,
    },
    { status: 404, headers: { 'content-type': 'application/problem+json' } },
  )
}

const server = setupServer()

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

function renderView(handle = 'ada') {
  return renderWithProviders(
    <Routes>
      <Route path="/user/:handle" element={<ProfileView />} />
    </Routes>,
    { initialEntries: [`/user/${handle}`], baseUrl: BASE },
  )
}

describe('ProfileView', () => {
  it('renders the display name, mono handle, and a grid of published-public cards', async () => {
    server.use(
      http.get('*/users/:handle', () =>
        HttpResponse.json({
          handle: 'ada',
          display_name: 'Ada Lovelace',
          roadmaps: [
            {
              id: 'grokking-dsa-7f3k',
              title: 'Grokking DSA',
              status: 'published',
              visibility: 'public',
              subject_tags: ['cs'],
            },
          ],
        }),
      ),
    )
    renderView()

    expect(await screen.findByRole('heading', { name: 'Ada Lovelace' })).toBeInTheDocument()
    expect(screen.getByText('@ada')).toBeInTheDocument()
    expect(screen.getByText('Grokking DSA')).toBeInTheDocument()
    // A published-public card shows its badges.
    expect(screen.getByText('Published')).toBeInTheDocument()
    expect(screen.getByText('Public')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Grokking DSA/ })).toHaveAttribute(
      'href',
      '/roadmaps/grokking-dsa-7f3k',
    )
  })

  it('shows the empty state but keeps the header when there are no public roadmaps', async () => {
    server.use(
      http.get('*/users/:handle', () =>
        HttpResponse.json({ handle: 'ada', display_name: 'Ada Lovelace', roadmaps: [] }),
      ),
    )
    renderView()

    expect(await screen.findByText('No published roadmaps yet.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Ada Lovelace' })).toBeInTheDocument()
    expect(screen.getByText('@ada')).toBeInTheDocument()
  })

  it('renders a 404 view for an unknown handle', async () => {
    server.use(http.get('*/users/:handle', ({ params }) => notFound(params.handle as string)))
    renderView('nobody')

    expect(await screen.findByText('No such profile.')).toBeInTheDocument()
    expect(screen.getByText('@nobody')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Back to Wren' })).toHaveAttribute('href', '/')
  })

  it('surfaces a load error with a retry that refetches', async () => {
    server.use(
      http.get('*/users/:handle', () => new HttpResponse(null, { status: 500 }), { once: true }),
    )
    renderView()

    expect(await screen.findByText(/couldn’t load this profile/i)).toBeInTheDocument()

    server.use(
      http.get('*/users/:handle', () =>
        HttpResponse.json({ handle: 'ada', display_name: 'Ada Lovelace', roadmaps: [] }),
      ),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Ada Lovelace' })).toBeInTheDocument(),
    )
  })
})
