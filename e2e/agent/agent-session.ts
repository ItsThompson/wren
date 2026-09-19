import { Client } from '@modelcontextprotocol/sdk/client/index.js'
import { UnauthorizedError } from '@modelcontextprotocol/sdk/client/auth.js'
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js'
import type { FetchLike } from '@modelcontextprotocol/sdk/shared/transport.js'

import { createCallbackListener } from '../fixtures/callback-listener'
import { createOAuthProvider, type E2EOAuthProvider } from './oauth-provider'
import type {
  AgentCallbackListener,
  AgentSession,
  AgentSessionRequest,
  AdvertisedTool,
  McpClientFactory,
  McpClientLike,
  McpTransportFactory,
  McpTransportLike,
} from './types'

export interface AgentSessionDependencies {
  createClient?: McpClientFactory['create']
  createTransport?: McpTransportFactory['create']
  createCallbackListener?: () => Promise<AgentCallbackListener>
  callbackTimeoutMs?: number
}

export async function createAgentSession(
  request: AgentSessionRequest,
  dependencies: AgentSessionDependencies = {},
): Promise<AgentSession> {
  const createListener = dependencies.createCallbackListener ?? (() => createCallbackListener(request.identity, request.contextOwner))
  const listener = await createListener()
  let provider: E2EOAuthProvider
  try {
    provider = createOAuthProvider({
      callbackUrl: new URL(listener.callbackUrl),
      clientName: `e2e-${request.identity.resourcePrefix}-mcp`,
      requestedScopes: request.requestedScopes,
      resourceUrl: new URL(request.mcpServerUrl.origin),
      sensitiveValues: request.sensitiveValues,
    })
  } catch (error: unknown) {
    await closeSetupResources(listener, undefined, error)
    throw error
  }

  let client: McpClientLike
  try {
    client = (dependencies.createClient ?? createDefaultClient)(provider.clientName)
  } catch (error: unknown) {
    await closeSetupResources(listener, provider, error)
    throw error
  }
  const transportFactory = dependencies.createTransport ?? createDefaultTransport
  const transports: McpTransportLike[] = []
  let closed = false
  let clientNeedsClose = false

  const closeClient = async (): Promise<void> => {
    if (!clientNeedsClose) return
    await client.close()
    clientNeedsClose = false
  }

  const closeResources = async (): Promise<void> => {
    if (closed) return
    closed = true
    const failures: unknown[] = []
    try {
      await closeClient()
    } catch (error: unknown) {
      failures.push(error)
    }
    for (const transport of [...transports].reverse()) {
      try {
        await transport.close()
      } catch (error: unknown) {
        failures.push(error)
      }
    }
    try {
      await listener.close()
    } catch (error: unknown) {
      failures.push(error)
    }
    provider.clear()
    if (failures.length > 0) throw new AggregateError(failures, 'agent session cleanup failed')
  }

  try {
    const initialTransport = transportFactory(request.mcpServerUrl, provider)
    transports.push(initialTransport)
    try {
      clientNeedsClose = true
      await client.connect(initialTransport)
      throw new Error('MCP server accepted an unauthenticated connection')
    } catch (error: unknown) {
      if (!(error instanceof UnauthorizedError)) throw error
      await closeClient()
    }

    const authorizationUrl = provider.getAuthorizationUrl()
    await approveConsent(request, authorizationUrl, provider)
    const callbackUrl = await listener.waitForCallback(dependencies.callbackTimeoutMs)
    provider.validateCallback(callbackUrl)
    const authorizationCode = callbackUrl.searchParams.get('code')
    if (authorizationCode === null) throw new Error('validated OAuth callback lost its authorization code')
    await initialTransport.finishAuth(authorizationCode)
    await initialTransport.close()
    const initialTransportIndex = transports.indexOf(initialTransport)
    if (initialTransportIndex >= 0) transports.splice(initialTransportIndex, 1)

    const freshTransport = transportFactory(request.mcpServerUrl, provider)
    transports.push(freshTransport)
    clientNeedsClose = true
    await client.connect(freshTransport)

    const authorization = provider.getAuthorization()
    return {
      authorization,
      listTools: async (): Promise<readonly AdvertisedTool[]> => {
        const result = await client.listTools()
        return result.tools
      },
      callTool: async <TOutput>(name: string, arguments_: Record<string, unknown>): Promise<TOutput> => {
        const result = await client.callTool({ name, arguments: arguments_ })
        return result as TOutput
      },
      waitUntilCurrentAccessTokenExpires: async (): Promise<void> => {
        await waitUntil(accessTokenExpiry(provider))
      },
      close: closeResources,
    }
  } catch (error: unknown) {
    try {
      await closeResources()
    } catch (cleanupError: unknown) {
      throw new AggregateError([error, cleanupError], 'agent session setup and cleanup failed')
    }
    throw error
  }
}

async function approveConsent(
  request: AgentSessionRequest,
  authorizationUrl: URL,
  provider: E2EOAuthProvider,
): Promise<void> {
  await request.consentPage.goto(authorizationUrl.toString(), { waitUntil: 'domcontentloaded' })
  const clientName = request.consentPage.getByText(provider.clientName, { exact: true })
  await clientName.waitFor({ state: 'visible' })
  for (const scope of request.requestedScopes) {
    const scopeText = request.consentPage.getByText(scope, { exact: true })
    await scopeText.waitFor({ state: 'visible' })
  }
  const authorizeButton = request.consentPage.getByRole('button', { name: 'Authorize', exact: true })
  await authorizeButton.waitFor({ state: 'visible' })
  await authorizeButton.click()
}

async function closeSetupResources(
  listener: AgentCallbackListener,
  provider: E2EOAuthProvider | undefined,
  setupError: unknown,
): Promise<never> {
  const failures: unknown[] = []
  try {
    await listener.close()
  } catch (error: unknown) {
    failures.push(error)
  }
  try {
    provider?.clear()
  } catch (error: unknown) {
    failures.push(error)
  }
  if (failures.length > 0) throw new AggregateError([setupError, ...failures], 'agent session setup cleanup failed')
  throw setupError
}

function createDefaultClient(name: string): McpClientLike {
  const client = new Client({ name, version: 'e2e' })
  return {
    connect: (transport): Promise<void> => client.connect(transport.transport),
    listTools: (): Promise<{ tools: AdvertisedTool[] }> => client.listTools(),
    callTool: async <TOutput = Record<string, unknown>>(
      params: { name: string; arguments?: Record<string, unknown> },
    ): Promise<TOutput> => (await client.callTool(params)) as TOutput,
    close: (): Promise<void> => client.close(),
  }
}

function createDefaultTransport(serverUrl: URL, provider: E2EOAuthProvider): McpTransportLike {
  const transport = new StreamableHTTPClientTransport(serverUrl, {
    authProvider: provider,
    fetch: createScopeLimitedFetch(globalThis.fetch.bind(globalThis) as FetchLike, serverUrl, provider.requestedScopes),
  })
  return {
    transport,
    finishAuth: (authorizationCode): Promise<void> => transport.finishAuth(authorizationCode),
    close: (): Promise<void> => transport.close(),
  }
}

interface ProtectedResourceDocument {
  [key: string]: unknown
  scopes_supported?: unknown
}

export function createScopeLimitedFetch(
  baseFetch: FetchLike,
  serverUrl: URL,
  requestedScopes: readonly string[],
): FetchLike {
  return async (url, init): Promise<Response> => {
    const response = await baseFetch(url, init)
    const requestUrl = new URL(url)
    if (response.status === 401 || response.status === 403) return removeChallengeScope(response)
    if (requestUrl.origin !== serverUrl.origin || !requestUrl.pathname.includes('/.well-known/oauth-protected-resource')) {
      return response
    }
    if (!response.ok) return response
    const document = (await response.clone().json()) as ProtectedResourceDocument
    if (!Array.isArray(document.scopes_supported)) return response
    const advertisedScopes = document.scopes_supported.filter((scope): scope is string => typeof scope === 'string')
    const missingScopes = requestedScopes.filter((scope) => !advertisedScopes.includes(scope))
    if (missingScopes.length > 0) {
      throw new Error(`requested OAuth scope is not advertised by PRM: ${missingScopes.join(', ')}`)
    }
    return new Response(JSON.stringify({ ...document, scopes_supported: [...requestedScopes] }), {
      status: response.status,
      statusText: response.statusText,
      headers: response.headers,
    })
  }
}

function removeChallengeScope(response: Response): Response {
  const challenge = response.headers.get('www-authenticate')
  if (challenge === null || !/\bscope=/i.test(challenge)) return response
  const withoutScope = challenge.replace(/,?\s*scope=(?:"[^"]*"|[^,\s]+)/i, '')
  const headers = new Headers(response.headers)
  headers.set('www-authenticate', withoutScope)
  return new Response(response.body, { status: response.status, statusText: response.statusText, headers })
}

const ACCESS_TOKEN_EXPIRY_MARGIN_MS = 1_000
const ACCESS_TOKEN_EXPIRY_WAIT_LIMIT_MS = 30_000

function accessTokenExpiry(provider: E2EOAuthProvider): number {
  return provider.getAuthorization().accessTokenExpiresAtEpochMs
}

async function waitUntil(expiryEpochMs: number): Promise<void> {
  const deadline = Math.min(
    expiryEpochMs + ACCESS_TOKEN_EXPIRY_MARGIN_MS,
    Date.now() + ACCESS_TOKEN_EXPIRY_WAIT_LIMIT_MS,
  )
  while (Date.now() < deadline) {
    await new Promise<void>((resolve) => {
      const timeout = setTimeout(resolve, Math.min(100, deadline - Date.now()))
      timeout.unref()
    })
  }
}
