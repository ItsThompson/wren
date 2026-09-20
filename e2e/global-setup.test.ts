import { afterEach, describe, expect, it, vi } from 'vitest'

import { fetchWithTimeout, type ReadinessFetcher, waitFor } from './global-setup'

afterEach(() => {
  vi.useRealTimers()
})

describe('readiness probes', () => {
  it('aborts a request at its injected per-request timeout', async () => {
    vi.useFakeTimers()
    let requestSignal: AbortSignal | undefined
    const fetcher: ReadinessFetcher = async (_url, init) => {
      requestSignal = init?.signal ?? undefined
      return new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener(
          'abort',
          () => reject(new DOMException('The readiness request timed out', 'AbortError')),
          { once: true },
        )
      })
    }

    const pending = fetchWithTimeout('https://app.wren.test/', {}, 100, fetcher)
    await vi.advanceTimersByTimeAsync(99)
    expect(requestSignal?.aborted).toBe(false)

    const rejected = pending.catch((error: unknown) => error)
    await vi.advanceTimersByTimeAsync(1)
    await expect(rejected).resolves.toMatchObject({ name: 'AbortError' })
    expect(requestSignal?.aborted).toBe(true)
  })

  it('keeps retries inside the declared readiness window without real sleeps', async () => {
    let elapsedMs = 0
    const check = vi.fn(async (requestTimeoutMs: number) => {
      expect(requestTimeoutMs).toBe(15)
      return false
    })
    const sleep = async (milliseconds: number) => {
      elapsedMs += milliseconds
    }

    await expect(
      waitFor('test-probe', check, {
        maxAttempts: 3,
        intervalMs: 20,
        requestTimeoutMs: 15,
        sleep,
        now: () => elapsedMs,
      }),
    ).rejects.toThrow('test-probe did not become ready within 0.06s')
    expect(check).toHaveBeenCalledTimes(3)
    expect(elapsedMs).toBe(60)
  })
})
