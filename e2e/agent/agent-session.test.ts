import { UnauthorizedError } from '@modelcontextprotocol/sdk/client/auth.js'
import type { Transport } from '@modelcontextprotocol/sdk/shared/transport.js'
import { describe, expect, it, vi } from 'vitest'

import { InMemorySensitiveValueRegistry } from '../fixtures/sensitive-value-registry.ts'
import { createAttemptIdentity } from '../fixtures/attempt-identity.ts'
import type { AgentCallbackListener, McpClientLike, McpTransportLike } from './types.ts'
import type { AgentSessionDependencies } from './agent-session.ts'
import { OAuthScope } from './types.ts'
import { createAgentSession } from './agent-session.ts'

function buildPage() {
  const visible = { isVisible: vi.fn(async () => true) }
  const authorizeButton = { ...visible, click: vi.fn(async () => undefined) }
  return {
    page: {
      goto: vi.fn(async () => undefined),
      getByText: vi.fn(() => visible),
      getByRole: vi.fn(() => authorizeButton),
    },
    authorizeButton,
  }
}

function buildListener(callbackUrl: URL, readState: () => string): AgentCallbackListener {
  return {
    callbackUrl,
    waitForCallback: vi.fn(async () => new URL(`${callbackUrl}?code=code-value&state=${readState()}`)),
    close: vi.fn(async () => undefined),
  }
}

describe('AgentSession', () => {
  it('uses the SDK authorization boundary, then reconnects with a fresh transport', async () => {
    const { page, authorizeButton } = buildPage()
    let callbackState = ''
    const listener = buildListener(new URL('http://127.0.0.1:43210/callback'), () => callbackState)
    const sensitiveValues = new InMemorySensitiveValueRegistry()
    const transports: McpTransportLike[] = []
    let firstFinishAuth: ReturnType<typeof vi.fn> | undefined
    let oauthProvider: Parameters<NonNullable<AgentSessionDependencies['createTransport']>>[1]
    const connect = vi.fn(async (transport: McpTransportLike) => {
      if (transports.indexOf(transport) === 0) {
        callbackState = (await oauthProvider?.state?.()) ?? ''
        await oauthProvider?.redirectToAuthorization?.(new URL('https://api.wren.test/authorize'))
        throw new UnauthorizedError()
      }
    })
    const client: McpClientLike = {
      connect,
      listTools: vi.fn(async () => ({ tools: [{ name: 'roadmap_get', inputSchema: { type: 'object' } }] })),
      callTool: vi.fn(async () => ({ structuredContent: { id: 'roadmap-1' } })) as McpClientLike['callTool'],
      close: vi.fn(async () => undefined),
    }
    const session = await createAgentSession(
      {
        identity: createAttemptIdentity({
          runId: 'run',
          projectName: 'chromium',
          file: 'agent-session.spec.ts',
          title: 'connect',
          parallelIndex: 0,
          retry: 0,
          nonce: 'nonce',
        }),
        consentPage: page as never,
        requestedScopes: [OAuthScope.ROADMAPS_READ],
        mcpServerUrl: new URL('https://mcp.wren.test'),
        sensitiveValues,
        contextOwner: { own: <T>(resource: T): T => resource, closeAll: async () => undefined },
      },
      {
        createCallbackListener: async () => listener,
        createClient: () => client,
        createTransport: (_serverUrl, provider) => {
          oauthProvider = provider
          const finishAuth = vi.fn(async () => {
            await provider.saveClientInformation?.({ client_id: 'client-id' })
            await provider.saveDiscoveryState?.({ authorizationServerUrl: 'https://api.wren.test' })
            await provider.saveTokens({ access_token: 'access-token', refresh_token: 'refresh-token', token_type: 'Bearer', expires_in: 1 })
          })
          const transport: McpTransportLike = {
            transport: {} as Transport,
            finishAuth,
            close: vi.fn(async () => undefined),
          }
          if (transports.length === 0) firstFinishAuth = finishAuth
          transports.push(transport)
          return transport
        },
      },
    )

    expect(authorizeButton.click).toHaveBeenCalledOnce()
    expect(connect).toHaveBeenCalledTimes(2)
    expect(transports).toHaveLength(2)
    expect(firstFinishAuth).toHaveBeenCalledWith('code-value')
    expect(session.authorization.clientId).toBe('client-id')
    await expect(session.listTools()).resolves.toEqual([{ name: 'roadmap_get', inputSchema: { type: 'object' } }])
    await expect(session.callTool('roadmap_get', { roadmap_id: 'roadmap-1' })).resolves.toEqual({ structuredContent: { id: 'roadmap-1' } })
    await session.close()
    expect(sensitiveValues.values()).toEqual([])
  })
})
