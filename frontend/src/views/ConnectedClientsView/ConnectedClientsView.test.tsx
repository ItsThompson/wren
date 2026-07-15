import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'

import { AuthProvider } from '@/auth'
import type { ConnectedClient } from './types'
import { ConnectedClientsView } from './ConnectedClientsView'

const BASE = 'https://api.test'

const AUTH_USER = {
  id: 'user-1',
  username: 'ada',
  email: 'ada@example.com',
  created_at: '2026-07-15T00:00:00Z',
}

const authedRefresh = () => http.post('*/auth/refresh', () => HttpResponse.json(AUTH_USER))
const anonRefresh = () =>
  http.post('*/auth/refresh', () => new HttpResponse(null, { status: 401 }))

function buildClient(overrides: Partial<ConnectedClient> = {}): ConnectedClient {
  return {
    client_id: 'client-abc',
    client_name: 'Claude Desktop',
    scopes: ['roadmaps:read', 'progress:write'],
    last_authorized: '2026-07-10T00:00:00Z',
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
      <MemoryRouter initialEntries={['/settings/connections']}>
        <Routes>
          <Route path="/settings/connections" element={<ConnectedClientsView baseUrl={BASE} />} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  )
}

describe('ConnectedClientsView', () => {
  it('lists each authorized client with its name, scopes, and last-authorized date', async () => {
    server.use(
      authedRefresh(),
      http.get('*/me/clients', () =>
        HttpResponse.json([
          buildClient(),
          buildClient({
            client_id: 'client-xyz',
            client_name: 'Research Agent',
            scopes: ['roadmaps:write'],
            last_authorized: '2026-06-01T00:00:00Z',
          }),
        ]),
      ),
    )
    // Loading skeleton shows first.
    renderView()
    expect(screen.getByLabelText('Loading connected agents')).toBeInTheDocument()

    expect(await screen.findByText('Claude Desktop')).toBeInTheDocument()
    expect(screen.getByText('Research Agent')).toBeInTheDocument()
    expect(screen.getAllByText(/Last authorized/).length).toBe(2)
    expect(screen.getByText('roadmaps:write')).toBeInTheDocument()
  })

  it('revokes a client after confirmation and removes it from the list', async () => {
    let deleted: string | null = null
    server.use(
      authedRefresh(),
      http.get('*/me/clients', () => HttpResponse.json([buildClient()])),
      http.delete('*/me/clients/:clientId', ({ params }) => {
        deleted = params.clientId as string
        return new HttpResponse(null, { status: 204 })
      }),
    )
    renderView()
    await screen.findByText('Claude Desktop')

    // Revoke is confirm-gated: first click reveals the destructive confirm.
    await userEvent.click(screen.getByRole('button', { name: 'Revoke' }))
    await userEvent.click(screen.getByRole('button', { name: 'Confirm revoke' }))

    await waitFor(() => expect(screen.queryByText('Claude Desktop')).not.toBeInTheDocument())
    expect(deleted).toBe('client-abc')
    // With no clients left, the empty state shows.
    expect(screen.getByText('No connected agents yet.')).toBeInTheDocument()
  })

  it('can cancel a pending revoke without deleting the client', async () => {
    server.use(
      authedRefresh(),
      http.get('*/me/clients', () => HttpResponse.json([buildClient()])),
    )
    renderView()
    await screen.findByText('Claude Desktop')

    await userEvent.click(screen.getByRole('button', { name: 'Revoke' }))
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    // Back to the un-confirmed state; the client remains.
    expect(screen.getByRole('button', { name: 'Revoke' })).toBeInTheDocument()
    expect(screen.getByText('Claude Desktop')).toBeInTheDocument()
  })

  it('keeps the client and shows an error when the revoke fails', async () => {
    server.use(
      authedRefresh(),
      http.get('*/me/clients', () => HttpResponse.json([buildClient()])),
      http.delete('*/me/clients/:clientId', () => new HttpResponse(null, { status: 500 })),
    )
    renderView()
    await screen.findByText('Claude Desktop')

    await userEvent.click(screen.getByRole('button', { name: 'Revoke' }))
    await userEvent.click(screen.getByRole('button', { name: 'Confirm revoke' }))

    expect(await screen.findByText(/Could not revoke this agent/i)).toBeInTheDocument()
    // The client stays, and the row returns to its un-confirmed state.
    expect(screen.getByText('Claude Desktop')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Revoke' })).toBeInTheDocument()
  })

  it('shows the empty state when there are no connected clients', async () => {
    server.use(authedRefresh(), http.get('*/me/clients', () => HttpResponse.json([])))
    renderView()

    expect(await screen.findByText('No connected agents yet.')).toBeInTheDocument()
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
      http.get('*/me/clients', () => new HttpResponse(null, { status: 500 }), { once: true }),
    )
    renderView()

    expect(await screen.findByText(/couldn’t load your connected agents/i)).toBeInTheDocument()

    // Retry now succeeds and renders the list.
    server.use(http.get('*/me/clients', () => HttpResponse.json([buildClient()])))
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))

    expect(await screen.findByText('Claude Desktop')).toBeInTheDocument()
  })
})
