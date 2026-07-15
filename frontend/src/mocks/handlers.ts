import { http, HttpResponse, delay } from 'msw'

import {
  mockAuthUser,
  mockDashboard,
  mockNext,
  mockOverview,
  mockProfile,
  mockProgress,
  mockRoadmap,
} from './data'
import type { MockProgressUpdateResult } from './types'

/**
 * MSW request handlers for the zero-backend dev harness (section 11 "Local
 * development", `npm run dev:mock`). Paths mirror the section-06 REST surface
 * and are prefixed with `*` so they match regardless of the client's API base
 * URL (relative in dev, absolute against `api.usewren.com` in prod).
 *
 * This is a representative read surface plus one write; feature slices extend it
 * as their views land. A modest fixed latency lets loading/skeleton states
 * render realistically in dev.
 */

const LATENCY_MS = 120

/** RFC 9457 problem-details body, matching the section-06 error contract. */
function notFound(instance: string) {
  return HttpResponse.json(
    {
      type: 'https://usewren.com/errors/not-found',
      title: 'Roadmap not found',
      status: 404,
      code: 'NOT_FOUND',
      instance,
    },
    { status: 404, headers: { 'content-type': 'application/problem+json' } },
  )
}

export const handlers = [
  // --- auth (section 06 external-only) ---
  // The mock harness starts anonymous: refresh has no session to resume. Login
  // and register return the demo user so the authed shell can be exercised.
  http.post('*/auth/refresh', () => new HttpResponse(null, { status: 401 })),

  http.post('*/auth/register', async () => {
    await delay(LATENCY_MS)
    return HttpResponse.json(mockAuthUser, { status: 201 })
  }),

  http.post('*/auth/login', async () => {
    await delay(LATENCY_MS)
    return HttpResponse.json(mockAuthUser)
  }),

  http.post('*/auth/logout', () => new HttpResponse(null, { status: 204 })),

  http.get('*/me/dashboard', async () => {
    await delay(LATENCY_MS)
    return HttpResponse.json(mockDashboard)
  }),

  http.get('*/users/:handle', async ({ params }) => {
    await delay(LATENCY_MS)
    if (params.handle !== mockProfile.handle) {
      return notFound(`/users/${params.handle as string}`)
    }
    return HttpResponse.json(mockProfile)
  }),

  http.get('*/roadmaps/:id', async ({ params }) => {
    await delay(LATENCY_MS)
    if (params.id !== mockRoadmap.id) {
      return notFound(`/roadmaps/${params.id as string}`)
    }
    return HttpResponse.json(mockRoadmap)
  }),

  http.get('*/roadmaps/:id/overview', async ({ params }) => {
    await delay(LATENCY_MS)
    if (params.id !== mockRoadmap.id) {
      return notFound(`/roadmaps/${params.id as string}/overview`)
    }
    return HttpResponse.json(mockOverview)
  }),

  http.get('*/roadmaps/:id/next', async ({ params }) => {
    await delay(LATENCY_MS)
    if (params.id !== mockRoadmap.id) {
      return notFound(`/roadmaps/${params.id as string}/next`)
    }
    return HttpResponse.json(mockNext)
  }),

  http.get('*/roadmaps/:id/progress', async ({ params }) => {
    await delay(LATENCY_MS)
    if (params.id !== mockRoadmap.id) {
      return notFound(`/roadmaps/${params.id as string}/progress`)
    }
    return HttpResponse.json(mockProgress)
  }),

  http.post('*/roadmaps/:id/progress', async ({ params }) => {
    await delay(LATENCY_MS)
    if (params.id !== mockRoadmap.id) {
      return notFound(`/roadmaps/${params.id as string}/progress`)
    }
    // Echo the current snapshot and next item; the harness does not persist.
    const result: MockProgressUpdateResult = {
      progress: mockProgress,
      next: mockNext,
    }
    return HttpResponse.json(result)
  }),
]
