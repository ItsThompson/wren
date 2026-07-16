import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, describe, expect, expectTypeOf, it, vi } from 'vitest'

import { makeTestApiClient } from '@/test/api-clients'

import { runQuery, type OpenApiResult } from './fetcher'

const BASE = 'https://api.test'

/**
 * A stand-in typed path. The generated `paths` holds only product routes, so it
 * is merged into the real `paths` via `makeTestApiClient`'s `Extra` type param,
 * exercising `runQuery` against a schema-typed body with no `as unknown as`
 * round-trip while every real route stays checked against `schema.d.ts`.
 */
interface WidgetPaths {
  '/widget': {
    get: { responses: { 200: { content: { 'application/json': { id: string } } } } }
  }
}

const server = setupServer()

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

function widgetClient() {
  return makeTestApiClient<WidgetPaths>(BASE)
}

describe('runQuery', () => {
  it('returns the typed body on a 200, inferred from the call thunk (no cast)', async () => {
    server.use(http.get('*/widget', () => HttpResponse.json({ id: 'w1' })))

    const data = await runQuery(() => widgetClient().GET('/widget'))

    expect(data).toEqual({ id: 'w1' })
    // AC7: `data` is inferred from the path literal, not `any`/`unknown`.
    expectTypeOf(data).toEqualTypeOf<{ id: string }>()
  })

  it('proves openapi-fetch returns { error } (not a throw) on a 404 and runQuery converts it to a thrown Problem (VC1)', async () => {
    server.use(
      http.get('*/widget', () =>
        HttpResponse.json(
          { type: 'about:blank', title: 'Not found', status: 404, code: 'NOT_FOUND' },
          { status: 404, headers: { 'content-type': 'application/problem+json' } },
        ),
      ),
    )

    // openapi-fetch RESOLVES (does not throw) with the parsed problem+json body.
    const raw = await widgetClient().GET('/widget')
    expect(raw.error).toEqual(expect.objectContaining({ status: 404, code: 'NOT_FOUND' }))
    expect(raw.data).toBeUndefined()
    expect(raw.response.status).toBe(404)

    // runQuery turns that resolved error into a thrown Problem whose status is
    // the response status.
    await expect(runQuery(() => widgetClient().GET('/widget'))).rejects.toMatchObject({
      status: 404,
      code: 'NOT_FOUND',
    })
  })

  it('throws a Problem whose status === response.status on a non-ok response with an empty body', async () => {
    server.use(http.get('*/widget', () => new HttpResponse(null, { status: 503 })))

    await expect(runQuery(() => widgetClient().GET('/widget'))).rejects.toMatchObject({
      status: 503,
      code: undefined,
    })
  })

  it('normalizes a network rejection to a thrown Problem with status: null', async () => {
    const call = (): Promise<OpenApiResult<{ id: string }>> =>
      Promise.reject(new TypeError('Failed to fetch'))

    await expect(runQuery(call)).rejects.toMatchObject({ status: null })
  })

  it('invokes the provided thunk exactly once and issues no request of its own', async () => {
    // A canned result: no network. With the MSW server set to error on any
    // unhandled request, runQuery completing proves it never calls raw fetch.
    const okResponse = new Response(null, { status: 200 })
    const call = vi.fn(
      (): Promise<OpenApiResult<{ id: string }>> =>
        Promise.resolve({ data: { id: 'x' }, response: okResponse }),
    )

    const data = await runQuery(call)

    expect(data).toEqual({ id: 'x' })
    expect(call).toHaveBeenCalledTimes(1)
  })
})
