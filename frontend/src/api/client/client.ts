import createClient, { type Client, type Middleware } from 'openapi-fetch'

import { createApiReportingMiddleware, type ApiReportingController } from '@/observability/sentry'
import type { paths } from '../schema'

export interface ApiClientOptions {
  credentials?: RequestCredentials
  /** Reporting controller for this client stack; one is created when omitted. */
  reporting?: ApiReportingController
  /**
   * Extra middleware registered after the reporting middleware, so its
   * `onResponse` runs first and can replace a response before reporting
   * classifies the final one.
   */
  middleware?: Middleware
}

export function createApiClient(baseUrl: string, clientOptions: ApiClientOptions = {}): Client<paths> {
  const client = createClient<paths>({
    baseUrl,
    credentials: clientOptions.credentials ?? 'omit',
  })
  client.use(clientOptions.reporting?.middleware ?? createApiReportingMiddleware().middleware)
  if (clientOptions.middleware) client.use(clientOptions.middleware)
  return client
}

export type ApiClient = Client<paths>
export type SessionClient = Client<paths>
