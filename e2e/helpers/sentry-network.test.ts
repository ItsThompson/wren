import { describe, expect, it } from 'vitest'

import { classifySentryRequest } from './sentry-network'

const localOrigin = 'https://app.wren.test'
const localIngestionPath = '/_e2e/sentry/api/1/envelope/'

describe('Sentry network policy', () => {
  it('rejects Sentry-owned hosts regardless of request path', () => {
    expect(classifySentryRequest('https://sentry.io/health', localOrigin, localIngestionPath)).toBe('unexpected-sentry')
    expect(classifySentryRequest('https://o123.ingest.sentry.io/store', localOrigin, localIngestionPath)).toBe('unexpected-sentry')
    expect(classifySentryRequest('https://sentry.dev/other', localOrigin, localIngestionPath)).toBe('unexpected-sentry')
  })

  it('allows only the configured local ingestion endpoint', () => {
    expect(classifySentryRequest(
      `${localOrigin}${localIngestionPath}`,
      localOrigin,
      localIngestionPath,
    )).toBe('local-ingestion')
    expect(classifySentryRequest(
      `${localOrigin}/api/1/envelope/`,
      localOrigin,
      localIngestionPath,
    )).toBe('other')
  })
})
