import { auth, UnauthorizedError } from '@modelcontextprotocol/sdk/client/auth.js'
import type { Transport } from '@modelcontextprotocol/sdk/shared/transport.js'
import { describe, expect, it, vi } from 'vitest'

import { InMemorySensitiveValueRegistry } from '../fixtures/sensitive-value-registry.ts'
import { createAttemptIdentity } from '../fixtures/attempt-identity.ts'
import type { AgentCallbackListener, McpClientLike, McpTransportLike } from './types.ts'
import type { AgentSessionDependencies } from './agent-session.ts'
import { OAuthScope } from './types.ts'
import { createAgentSession, createScopeLimitedFetch } from './agent-session.ts'
import { createOAuthProvider } from './oauth-provider.ts'

function buildPage() {
  const visible = {
    isVisible: vi.fn(async () => true),
    waitFor: vi.fn(async () => undefined),
  }
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

interface TestCallbackListener extends AgentCallbackListener {
  closeSpy: ReturnType<typeof vi.fn>
}

function buildListener(
  callbackUrl: URL,
  readState: () => string,
  buildQuery: (state: string) => string = (state) => `code=code-value&state=${state}`,
): TestCallbackListener {
  const closeSpy = vi.fn(async () => undefined)
  return {
    callbackUrl,
    waitForCallback: vi.fn(async () => new URL(`${callbackUrl}?${buildQuery(readState())}`)),
    close: closeSpy,
    closeSpy,
  }
}

describe('AgentSession', () => {
  it('closes the callback listener when provider setup fails', async () => {
    const { page } = buildPage()
    const listener = buildListener(new URL('http://127.0.0.1:43213/callback'), () => '')
    const sensitiveValues = new InMemorySensitiveValueRegistry()
    await expect(createAgentSession({
      identity: createAttemptIdentity({ runId: 'run', projectName: 'chromium', file: 'setup.spec.ts', title: 'provider failure', parallelIndex: 0, retry: 0, nonce: 'nonce' }),
      consentPage: page as never,
      requestedScopes: [],
      mcpServerUrl: new URL('https://mcp.wren.test/mcp'),
      sensitiveValues,
      contextOwner: { own: <T>(resource: T): T => resource, closeAll: async () => undefined },
    }, { createCallbackListener: async () => listener })).rejects.toThrow('at least one scope')
    expect(listener.closeSpy).toHaveBeenCalledOnce()
    expect(sensitiveValues.values()).toEqual([])
  })

  it('closes the callback listener when client setup fails', async () => {
    const { page } = buildPage()
    const listener = buildListener(new URL('http://127.0.0.1:43214/callback'), () => '')
    const sensitiveValues = new InMemorySensitiveValueRegistry()
    await expect(createAgentSession({
      identity: createAttemptIdentity({ runId: 'run', projectName: 'chromium', file: 'setup.spec.ts', title: 'client failure', parallelIndex: 0, retry: 0, nonce: 'nonce' }),
      consentPage: page as never,
      requestedScopes: [OAuthScope.ROADMAPS_READ],
      mcpServerUrl: new URL('https://mcp.wren.test/mcp'),
      sensitiveValues,
      contextOwner: { own: <T>(resource: T): T => resource, closeAll: async () => undefined },
    }, {
      createCallbackListener: async () => listener,
      createClient: () => { throw new Error('client setup failed') },
    })).rejects.toThrow('client setup failed')
    expect(listener.closeSpy).toHaveBeenCalledOnce()
    expect(sensitiveValues.values()).toEqual([])
  })

  it('limits SDK discovery scope to the requested subset of PRM scopes', async () => {
    const fetchPrm = createScopeLimitedFetch(
      async () => new Response(JSON.stringify({ scopes_supported: ['roadmaps:read', 'roadmaps:write'] })),
      new URL('https://mcp.wren.test'),
      ['roadmaps:read'],
    )
    const response = await fetchPrm('https://mcp.wren.test/.well-known/oauth-protected-resource')
    await expect(response.json()).resolves.toEqual({ scopes_supported: ['roadmaps:read'] })

    const fetchChallenge = createScopeLimitedFetch(
      async () => new Response(null, { status: 401, headers: { 'www-authenticate': 'Bearer scope="roadmaps:read roadmaps:write"' } }),
      new URL('https://mcp.wren.test'),
      ['roadmaps:read'],
    )
    const challenge = await fetchChallenge('https://mcp.wren.test/mcp')
    expect(challenge.headers.get('www-authenticate')).toBe('Bearer')
  })

  it('passes only requested scopes to SDK registration and authorization', async () => {
    const sensitiveValues = new InMemorySensitiveValueRegistry()
    const provider = createOAuthProvider({
      callbackUrl: new URL('http://127.0.0.1:43212/callback'),
      clientName: 'scope-test-client',
      requestedScopes: [OAuthScope.ROADMAPS_READ],
      resourceUrl: new URL('https://mcp.wren.test'),
      sensitiveValues,
    })
    const requests: { url: string; body: string }[] = []
    const baseFetch = async (url: string | URL, init?: RequestInit): Promise<Response> => {
      const requestUrl = new URL(url)
      requests.push({ url: requestUrl.toString(), body: typeof init?.body === 'string' ? init.body : '' })
      if (requestUrl.pathname.includes('/.well-known/oauth-protected-resource')) {
        return new Response(JSON.stringify({
          resource: 'https://mcp.wren.test',
          authorization_servers: ['https://api.wren.test'],
          bearer_methods_supported: ['header'],
          scopes_supported: ['roadmaps:read', 'roadmaps:write', 'progress:write'],
        }), { headers: { 'content-type': 'application/json' } })
      }
      if (requestUrl.pathname.endsWith('/.well-known/oauth-authorization-server')) {
        return new Response(JSON.stringify({
          issuer: 'https://api.wren.test',
          authorization_endpoint: 'https://api.wren.test/authorize',
          token_endpoint: 'https://api.wren.test/token',
          registration_endpoint: 'https://api.wren.test/register',
          response_types_supported: ['code'],
          grant_types_supported: ['authorization_code', 'refresh_token'],
          token_endpoint_auth_methods_supported: ['none'],
          code_challenge_methods_supported: ['S256'],
        }), { headers: { 'content-type': 'application/json' } })
      }
      if (requestUrl.pathname === '/register') {
        return new Response(JSON.stringify({
          client_id: 'scope-client-id',
          redirect_uris: ['http://127.0.0.1:43212/callback'],
          token_endpoint_auth_method: 'none',
          grant_types: ['authorization_code', 'refresh_token'],
          response_types: ['code'],
          client_name: 'scope-test-client',
          scope: 'roadmaps:read',
        }), { headers: { 'content-type': 'application/json' } })
      }
      throw new Error(`unexpected OAuth request: ${requestUrl}`)
    }

    await expect(auth(provider, {
      serverUrl: new URL('https://mcp.wren.test/mcp'),
      fetchFn: createScopeLimitedFetch(baseFetch, new URL('https://mcp.wren.test'), provider.requestedScopes),
    })).resolves.toBe('REDIRECT')

    const registration = JSON.parse(requests.find((request) => request.url.endsWith('/register'))?.body ?? '{}') as { scope?: string }
    const authorization = new URL(provider.getAuthorizationUrl())
    expect(registration.scope).toBe('roadmaps:read')
    expect(authorization.searchParams.get('scope')).toBe('roadmaps:read')
  })

  it('rejects a requested scope that PRM does not advertise', async () => {
    const fetchPrm = createScopeLimitedFetch(
      async () => new Response(JSON.stringify({ scopes_supported: ['roadmaps:read'] })),
      new URL('https://mcp.wren.test'),
      ['roadmaps:write'],
    )
    await expect(fetchPrm('https://mcp.wren.test/.well-known/oauth-protected-resource')).rejects.toThrow('not advertised')
  })

  it('closes owned resources when consent is denied', async () => {
    const { page } = buildPage()
    const listener = buildListener(
      new URL('http://127.0.0.1:43211/callback'),
      () => 'expected-state',
      (state) => `error=access_denied&state=${state}`,
    )
    const sensitiveValues = new InMemorySensitiveValueRegistry()
    let oauthProvider: Parameters<NonNullable<AgentSessionDependencies['createTransport']>>[1]
    const transportClose = vi.fn(async () => undefined)
    const clientClose = vi.fn(async () => undefined)
    const client: McpClientLike = {
      connect: vi.fn(async () => {
        const state = (await oauthProvider?.state?.()) ?? ''
        await oauthProvider?.redirectToAuthorization?.(new URL(`https://api.wren.test/authorize?state=${state}`))
        throw new UnauthorizedError()
      }),
      listTools: vi.fn(async () => ({ tools: [] })),
      callTool: vi.fn(async () => ({})) as McpClientLike['callTool'],
      close: clientClose,
    }
    await expect(createAgentSession(
      {
        identity: createAttemptIdentity({ runId: 'run', projectName: 'chromium', file: 'failure.spec.ts', title: 'cleanup', parallelIndex: 0, retry: 0, nonce: 'nonce' }),
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
          return { transport: {} as Transport, finishAuth: vi.fn(async () => undefined), close: transportClose }
        },
      },
    )).rejects.toThrow('authorization failed: access_denied')
    expect(clientClose).toHaveBeenCalledOnce()
    expect(transportClose).toHaveBeenCalledOnce()
    expect(listener.closeSpy).toHaveBeenCalledOnce()
    expect(sensitiveValues.values()).toEqual([])
  })

  it('uses the SDK authorization boundary, then reconnects with a fresh transport', async () => {
    const { page, authorizeButton } = buildPage()
    let callbackState = ''
    const listener = buildListener(new URL('http://127.0.0.1:43210/callback'), () => callbackState)
    const sensitiveValues = new InMemorySensitiveValueRegistry()
    const transports: McpTransportLike[] = []
    const transportCloseSpies: ReturnType<typeof vi.fn>[] = []
    let firstFinishAuth: ReturnType<typeof vi.fn> | undefined
    let oauthProvider: Parameters<NonNullable<AgentSessionDependencies['createTransport']>>[1]
    const clientClose = vi.fn(async () => undefined)
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
      close: clientClose,
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
          const close = vi.fn(async () => undefined)
          transportCloseSpies.push(close)
          const transport: McpTransportLike = {
            transport: {} as Transport,
            finishAuth,
            close,
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
    expect(clientClose).toHaveBeenCalledTimes(2)
    expect(listener.closeSpy).toHaveBeenCalledOnce()
    expect(transportCloseSpies).toHaveLength(2)
    expect(transportCloseSpies[0]).toHaveBeenCalledOnce()
    expect(transportCloseSpies[1]).toHaveBeenCalledOnce()
    expect(sensitiveValues.values()).toEqual([])
  })

  it('cleans up every owned resource when fresh transport initialization fails', async () => {
    const { page } = buildPage()
    let callbackState = ''
    const listener = buildListener(new URL('http://127.0.0.1:43209/callback'), () => callbackState)
    const sensitiveValues = new InMemorySensitiveValueRegistry()
    const transports: McpTransportLike[] = []
    const transportCloseSpies: ReturnType<typeof vi.fn>[] = []
    let oauthProvider: Parameters<NonNullable<AgentSessionDependencies['createTransport']>>[1]
    const clientClose = vi.fn(async () => undefined)
    const connect = vi.fn(async (transport: McpTransportLike) => {
      if (transports.indexOf(transport) === 0) {
        callbackState = (await oauthProvider?.state?.()) ?? ''
        await oauthProvider?.redirectToAuthorization?.(new URL('https://api.wren.test/authorize'))
        throw new UnauthorizedError()
      }
      throw new Error('fresh transport initialization failed')
    })
    const client: McpClientLike = {
      connect,
      listTools: vi.fn(async () => ({ tools: [] })),
      callTool: vi.fn(async () => ({})) as McpClientLike['callTool'],
      close: clientClose,
    }

    await expect(createAgentSession(
      {
        identity: createAttemptIdentity({ runId: 'run', projectName: 'chromium', file: 'failure.spec.ts', title: 'initialization failure', parallelIndex: 0, retry: 0, nonce: 'nonce' }),
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
            await provider.saveTokens({ access_token: 'access-token', token_type: 'Bearer', expires_in: 1 })
          })
          const close = vi.fn(async () => undefined)
          transportCloseSpies.push(close)
          const transport: McpTransportLike = {
            transport: {} as Transport,
            finishAuth,
            close,
          }
          transports.push(transport)
          return transport
        },
      },
    )).rejects.toThrow('fresh transport initialization failed')

    expect(connect).toHaveBeenCalledTimes(2)
    expect(clientClose).toHaveBeenCalledTimes(2)
    expect(listener.closeSpy).toHaveBeenCalledOnce()
    expect(transportCloseSpies).toHaveLength(2)
    expect(transportCloseSpies[0]).toHaveBeenCalledOnce()
    expect(transportCloseSpies[1]).toHaveBeenCalledOnce()
    expect(sensitiveValues.values()).toEqual([])
  })
})
