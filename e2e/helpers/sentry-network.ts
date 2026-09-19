const SENTRY_OWNED_HOST_SUFFIXES = ['.sentry.io', '.sentry.dev'] as const

export type SentryRequestClassification = 'local-ingestion' | 'unexpected-sentry' | 'other'

export function classifySentryRequest(
  requestUrl: string,
  localOrigin: string,
  localIngestionPath: string,
): SentryRequestClassification {
  const url = new URL(requestUrl)
  if (isSentryOwnedHost(url.hostname)) return 'unexpected-sentry'
  if (url.origin === localOrigin && url.pathname === localIngestionPath) return 'local-ingestion'
  return 'other'
}

function isSentryOwnedHost(hostname: string): boolean {
  const normalizedHostname = hostname.toLowerCase()
  return normalizedHostname === 'sentry.io'
    || normalizedHostname === 'sentry.dev'
    || SENTRY_OWNED_HOST_SUFFIXES.some((suffix) => normalizedHostname.endsWith(suffix))
}
