import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { Route, Routes } from 'react-router'
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/renderWithProviders'

import { ConsentView } from './ConsentView'

const BASE = 'https://api.test'
const AUTH_REQUEST_ID = 'req-123'
const APPROVE_REDIRECT = 'http://127.0.0.1:52001/callback?code=abc&state=xyz'
const DENY_REDIRECT = 'http://127.0.0.1:52001/callback?error=access_denied&state=xyz'

const AUTH_USER = {
  id: 'user-1',
  username: 'ada',
  email: 'ada@example.com',
  created_at: '2026-07-15T00:00:00Z',
}

/** AuthProvider resumes the session on mount; drive it authenticated / anonymous. */
const authedRefresh = () => http.post('*/auth/refresh', () => HttpResponse.json(AUTH_USER))
const anonRefresh = () =>
  http.post('*/auth/refresh', () => new HttpResponse(null, { status: 401 }))
const loginOk = () => http.post('*/auth/login', () => HttpResponse.json(AUTH_USER))

/** The parked-request context: known id resolves, anything else is expired (404). */
const contextOk = () =>
  http.get('*/authorize/context', ({ request }) => {
    const id = new URL(request.url).searchParams.get('auth_request_id')
    if (id !== AUTH_REQUEST_ID) {
      return new HttpResponse(null, { status: 404 })
    }
    return HttpResponse.json({
      client_name: 'Claude Desktop',
      scopes: ['roadmaps:read', 'roadmaps:write', 'progress:write'],
      authenticated: true,
    })
  })

/** The decision endpoint hands back the agent loopback URL as JSON. */
const decisionOk = () =>
  http.post('*/authorize/decision', async ({ request }) => {
    const body = (await request.json()) as { approve: boolean }
    return HttpResponse.json({ redirect_uri: body.approve ? APPROVE_REDIRECT : DENY_REDIRECT })
  })

const server = setupServer()

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

function renderConsent(options: { path?: string; navigateExternal?: (url: string) => void } = {}) {
  const { path = `/authorize?auth_request_id=${AUTH_REQUEST_ID}`, navigateExternal } = options
  return renderWithProviders(
    <Routes>
      <Route path="/authorize" element={<ConsentView navigateExternal={navigateExternal} />} />
    </Routes>,
    { initialEntries: [path], baseUrl: BASE, useRealAuth: true },
  )
}

describe('ConsentView', () => {
  it('shows a spinner, then renders the consent card for an authenticated session', async () => {
    server.use(authedRefresh(), contextOk())
    renderConsent()

    // The loading state renders while the context + session resolve.
    expect(screen.getByLabelText('Loading consent request')).toBeInTheDocument()

    // The trust sentence names the agent and the signed-in user.
    expect(await screen.findByText(/wants to act as/i)).toBeInTheDocument()
    expect(screen.getByText('Claude Desktop')).toBeInTheDocument()
    expect(screen.getByText('ada')).toBeInTheDocument()

    // Requested scopes appear as a plain list (raw tokens shown).
    expect(screen.getByText('roadmaps:read')).toBeInTheDocument()
    expect(screen.getByText('roadmaps:write')).toBeInTheDocument()
    expect(screen.getByText('progress:write')).toBeInTheDocument()

    // Primary Authorize + ghost Deny.
    expect(screen.getByRole('button', { name: 'Authorize' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Deny' })).toBeInTheDocument()
  })

  it('prompts login when there is no session, then returns to the decision', async () => {
    server.use(anonRefresh(), contextOk(), loginOk())
    renderConsent()

    // Anonymous: the login gate shows instead of the decision.
    expect(await screen.findByText('Log in to continue')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Authorize' })).not.toBeInTheDocument()

    // Log in; the provider flips to authenticated and the card appears.
    await userEvent.type(screen.getByLabelText('Email'), 'ada@example.com')
    await userEvent.type(screen.getByLabelText('Password'), 'correct horse')
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }))

    expect(await screen.findByText(/wants to act as/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Authorize' })).toBeInTheDocument()
  })

  it('can toggle the login gate to the register form', async () => {
    server.use(anonRefresh(), contextOk())
    renderConsent()

    await screen.findByText('Log in to continue')
    await userEvent.click(screen.getByRole('button', { name: 'Create an account' }))

    // The register form adds a username field.
    expect(screen.getByLabelText('Username')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create account' })).toBeInTheDocument()
  })

  it('authorizes: navigates the browser to the agent loopback URL', async () => {
    const navigateExternal = vi.fn()
    server.use(authedRefresh(), contextOk(), decisionOk())
    renderConsent({ navigateExternal })

    await userEvent.click(await screen.findByRole('button', { name: 'Authorize' }))

    await waitFor(() => expect(navigateExternal).toHaveBeenCalledWith(APPROVE_REDIRECT))
  })

  it('denies: navigates to the access_denied loopback URL', async () => {
    const navigateExternal = vi.fn()
    server.use(authedRefresh(), contextOk(), decisionOk())
    renderConsent({ navigateExternal })

    await userEvent.click(await screen.findByRole('button', { name: 'Deny' }))

    await waitFor(() => expect(navigateExternal).toHaveBeenCalledWith(DENY_REDIRECT))
  })

  it('shows an inline error when the decision request fails', async () => {
    const navigateExternal = vi.fn()
    server.use(
      authedRefresh(),
      contextOk(),
      http.post('*/authorize/decision', () => new HttpResponse(null, { status: 500 })),
    )
    renderConsent({ navigateExternal })

    await userEvent.click(await screen.findByRole('button', { name: 'Authorize' }))

    expect(await screen.findByText('Something went wrong. Please try again.')).toBeInTheDocument()
    expect(navigateExternal).not.toHaveBeenCalled()
  })

  it('collapses to the expired state when the decision reports the request is gone', async () => {
    const navigateExternal = vi.fn()
    server.use(
      authedRefresh(),
      contextOk(),
      http.post('*/authorize/decision', () => new HttpResponse(null, { status: 404 })),
    )
    renderConsent({ navigateExternal })

    await userEvent.click(await screen.findByRole('button', { name: 'Authorize' }))

    expect(
      await screen.findByText('This request expired: reconnect from your agent.'),
    ).toBeInTheDocument()
    expect(navigateExternal).not.toHaveBeenCalled()
  })

  it('renders the expired state for an unknown/expired auth_request_id', async () => {
    server.use(anonRefresh(), contextOk())
    renderConsent({ path: '/authorize?auth_request_id=stale' })

    expect(
      await screen.findByText('This request expired: reconnect from your agent.'),
    ).toBeInTheDocument()
  })

  it('renders the expired state when auth_request_id is missing entirely', async () => {
    server.use(anonRefresh())
    renderConsent({ path: '/authorize' })

    expect(
      await screen.findByText('This request expired: reconnect from your agent.'),
    ).toBeInTheDocument()
  })
})
