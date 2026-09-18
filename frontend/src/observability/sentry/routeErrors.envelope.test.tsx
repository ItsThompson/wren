import { StrictMode } from 'react'

import * as Sentry from '@sentry/react'
import { render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider, type RouteObject } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AppErrorBoundary } from '@/components/AppErrorBoundary'
import { ErrorBoundaryFallback } from '@/components/ErrorBoundaryFallback'
import { TEST_SENTRY_DSN, makeRecordingTransport } from '@/test/sentryRecording'

import { beforeSendSentryEvent } from './init'
import { reportRouteError } from './report'

const events: Sentry.Event[] = []

function BrokenRoute(): null {
  throw new Error('route render failed')
}

function initRecordingTransport(): void {
  Sentry.init({
    dsn: TEST_SENTRY_DSN,
    transport: makeRecordingTransport(events),
    beforeSend: beforeSendSentryEvent,
    sendDefaultPii: false,
    defaultIntegrations: [],
    integrations: [Sentry.linkedErrorsIntegration()],
    enableLogs: false,
    maxBreadcrumbs: 0,
    tracesSampleRate: 0,
    replaysSessionSampleRate: 0,
    replaysOnErrorSampleRate: 0,
  })
}

function renderRouter(route: RouteObject) {
  const router = createMemoryRouter([
    {
      ...route,
      path: '/',
      errorElement: <ErrorBoundaryFallback />,
    },
  ])
  render(
    <StrictMode>
      <AppErrorBoundary>
        <RouterProvider router={router} onError={reportRouteError} />
      </AppErrorBoundary>
    </StrictMode>,
  )
  return router
}

async function expectOneSafeRouteError(): Promise<void> {
  expect(await screen.findByRole('alert')).toHaveTextContent('Something went wrong')
  expect(screen.queryByText(/route (render|loader|action|middleware) failed/)).not.toBeInTheDocument()
  expect(screen.queryByText('Unexpected Application Error!')).not.toBeInTheDocument()
  await Sentry.flush()

  expect(events).toHaveLength(1)
  expect(events[0].tags?.['api.operation']).toBe('route.app')
  expect(events[0].tags?.['api.failure_kind']).toBe('internal')
  expect(events[0].fingerprint).toEqual(['route.app', 'internal', '{{ default }}'])
}

describe('React Router error reporting with the real SDK', () => {
  beforeEach(() => {
    events.length = 0
    initRecordingTransport()
    vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  afterEach(async () => {
    await Sentry.close()
    vi.restoreAllMocks()
  })

  it('captures a route render error once and renders the safe route fallback', async () => {
    renderRouter({ element: <BrokenRoute /> })
    await expectOneSafeRouteError()
  })

  it.each([
    ['loader', { loader: () => { throw new Error('route loader failed') } }],
    ['middleware', { middleware: [() => { throw new Error('route middleware failed') }] }],
  ] satisfies Array<[string, RouteObject]>)('captures a route %s error once', async (_, route) => {
    renderRouter({ ...route, element: <p>Route content</p> })
    await expectOneSafeRouteError()
  })

  it('captures a route action error once', async () => {
    const router = renderRouter({
      action: () => {
        throw new Error('route action failed')
      },
      element: <p>Route content</p>,
    })

    await router.navigate('/', { formData: new FormData(), formMethod: 'post' })
    await expectOneSafeRouteError()
  })
})
