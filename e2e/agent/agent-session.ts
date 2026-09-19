import { Client } from '@modelcontextprotocol/sdk/client/index.js'
import { UnauthorizedError } from '@modelcontextprotocol/sdk/client/auth.js'
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js'

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
  const createListener = dependencies.createCallbackListener ?? (() => {
    if (request.contextOwner === undefined) {
      throw new Error('agent session requires a context owner for its callback listener')
    }
    return createCallbackListener(request.identity, request.contextOwner)
  })
  const listener = await createListener()
  const provider = createOAuthProvider({
    callbackUrl: new URL(listener.callbackUrl),
    clientName: `e2e-${request.identity.resourcePrefix}-mcp`,
    requestedScopes: request.requestedScopes,
    resourceUrl: request.mcpServerUrl,
    sensitiveValues: request.sensitiveValues,
  })
  const client = (dependencies.createClient ?? createDefaultClient)(provider.clientName)
  const transportFactory = dependencies.createTransport ?? createDefaultTransport
  const transports: McpTransportLike[] = []
  let closed = false

  const closeResources = async (): Promise<void> => {
    if (closed) return
    closed = true
    const failures: unknown[] = []
    try {
      await client.close()
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
      await client.connect(initialTransport)
      throw new Error('MCP server accepted an unauthenticated connection')
    } catch (error: unknown) {
      if (!(error instanceof UnauthorizedError)) throw error
      await client.close()
    }

    const authorizationUrl = provider.getAuthorizationUrl()
    await approveConsent(request, authorizationUrl, provider)
    const callbackUrl = await listener.waitForCallback(dependencies.callbackTimeoutMs)
    provider.validateCallback(callbackUrl)
    const authorizationCode = callbackUrl.searchParams.get('code')
    if (authorizationCode === null) throw new Error('validated OAuth callback lost its authorization code')
    await initialTransport.finishAuth(authorizationCode)
    await initialTransport.close()

    const freshTransport = transportFactory(request.mcpServerUrl, provider)
    transports.push(freshTransport)
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
  if (!(await clientName.isVisible())) throw new Error('OAuth consent page did not show the client name')
  for (const scope of request.requestedScopes) {
    const scopeText = request.consentPage.getByText(scope, { exact: true })
    if (!(await scopeText.isVisible())) throw new Error(`OAuth consent page did not show scope ${scope}`)
  }
  const authorizeButton = request.consentPage.getByRole('button', { name: 'Authorize', exact: true })
  if (!(await authorizeButton.isVisible())) throw new Error('OAuth consent page did not show its approval control')
  await authorizeButton.click()
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
  const transport = new StreamableHTTPClientTransport(serverUrl, { authProvider: provider })
  return {
    transport,
    finishAuth: (authorizationCode): Promise<void> => transport.finishAuth(authorizationCode),
    close: (): Promise<void> => transport.close(),
  }
}

function accessTokenExpiry(provider: E2EOAuthProvider): number {
  return provider.getAuthorization().accessTokenExpiresAtEpochMs
}

async function waitUntil(expiryEpochMs: number): Promise<void> {
  const deadline = Math.min(expiryEpochMs + 250, Date.now() + 30_000)
  while (Date.now() < deadline) {
    await new Promise<void>((resolve) => {
      const timeout = setTimeout(resolve, Math.min(100, deadline - Date.now()))
      timeout.unref()
    })
  }
}
