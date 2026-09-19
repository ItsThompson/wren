import { describe, expect, it } from 'vitest'

import { InMemorySensitiveValueRegistry } from '../fixtures/sensitive-value-registry.ts'
import { OAuthScope } from './types.ts'
import { createOAuthProvider } from './oauth-provider.ts'

function buildProvider() {
  const sensitiveValues = new InMemorySensitiveValueRegistry()
  const provider = createOAuthProvider({
    callbackUrl: new URL('http://127.0.0.1:43123/callback'),
    clientName: 'e2e-attempt-client',
    requestedScopes: [OAuthScope.ROADMAPS_READ],
    resourceUrl: new URL('https://mcp.wren.test'),
    sensitiveValues,
  })
  return { provider, sensitiveValues }
}

describe('E2EOAuthProvider', () => {
  it('stores public registration metadata and keeps authorization values private', async () => {
    const { provider, sensitiveValues } = buildProvider()
    const state = await provider.state!()
    await provider.saveCodeVerifier('verifier-value')
    await provider.saveClientInformation!({ client_id: 'client-id' })
    await provider.redirectToAuthorization(new URL('https://api.wren.test/authorize?state=one'))

    expect(provider.clientMetadata).toMatchObject({
      client_name: 'e2e-attempt-client',
      redirect_uris: ['http://127.0.0.1:43123/callback'],
      token_endpoint_auth_method: 'none',
      scope: 'roadmaps:read',
    })
    expect(provider.getAuthorizationUrl().origin).toBe('https://api.wren.test')
    expect(state).toEqual(expect.any(String))
    expect(provider.codeVerifier()).toBe('verifier-value')
    expect(sensitiveValues.values()).toContain('verifier-value')
  })

  it('validates callback state before registering the authorization code', async () => {
    const { provider, sensitiveValues } = buildProvider()
    const state = await provider.state!()
    const callbackUrl = new URL(`http://127.0.0.1:43123/callback?code=code-value&state=${state}`)

    expect(provider.validateCallback(callbackUrl).state).toBe(state)
    expect(sensitiveValues.values()).toContain('code-value')

    const invalidCallback = new URL('http://127.0.0.1:43123/callback?code=bad-code&state=wrong')
    expect(() => provider.validateCallback(invalidCallback)).toThrow('state')
    expect(sensitiveValues.values()).not.toContain('bad-code')
  })

  it('rejects callback issuers that are missing or differ from discovery', async () => {
    const missingDiscovery = buildProvider()
    const missingState = await missingDiscovery.provider.state!()
    expect(() => missingDiscovery.provider.validateCallback(new URL(
      `http://127.0.0.1:43123/callback?code=code-value&state=${missingState}&iss=https%3A%2F%2Fapi.wren.test`,
    ))).toThrow('cannot be validated')

    const mismatched = buildProvider()
    const state = await mismatched.provider.state!()
    await mismatched.provider.saveDiscoveryState!({ authorizationServerUrl: 'https://api.wren.test' })
    expect(() => mismatched.provider.validateCallback(new URL(
      `http://127.0.0.1:43123/callback?code=code-value&state=${state}&iss=https%3A%2F%2Fevil.test`,
    ))).toThrow('did not match')
    expect(mismatched.sensitiveValues.values()).not.toContain('code-value')
  })

  it('exposes safe authorization metadata and erases sensitive state on clear', async () => {
    const { provider, sensitiveValues } = buildProvider()
    await provider.state!()
    await provider.saveClientInformation!({ client_id: 'client-id' })
    await provider.saveDiscoveryState!({ authorizationServerUrl: 'https://api.wren.test' })
    await provider.saveTokens({ access_token: 'access-token', refresh_token: 'refresh-token', token_type: 'Bearer', expires_in: 2 })

    expect(provider.getAuthorization()).toMatchObject({
      issuer: 'https://api.wren.test',
      clientId: 'client-id',
      clientName: 'e2e-attempt-client',
      grantedScopes: [OAuthScope.ROADMAPS_READ],
      hasRefreshToken: true,
    })
    expect(sensitiveValues.values()).toEqual(expect.arrayContaining(['access-token', 'refresh-token']))

    provider.clear()
    expect(sensitiveValues.values()).toEqual([])
    expect(provider.clientInformation()).toBeUndefined()
    expect(provider.tokens()).toBeUndefined()
  })

  it('preserves OAuth values in the snapshot sink after live state cleanup', async () => {
    const snapshot = new InMemorySensitiveValueRegistry()
    const live = new InMemorySensitiveValueRegistry(snapshot)
    const provider = createOAuthProvider({
      callbackUrl: new URL('http://127.0.0.1:43123/callback'),
      clientName: 'e2e-attempt-client',
      requestedScopes: [OAuthScope.ROADMAPS_READ],
      resourceUrl: new URL('https://mcp.wren.test'),
      sensitiveValues: live,
    })
    await provider.state!()
    await provider.saveCodeVerifier('verifier-value')
    await provider.saveTokens({ access_token: 'access-token', refresh_token: 'refresh-token', token_type: 'Bearer', expires_in: 2 })

    provider.clear()

    expect(live.values()).toEqual([])
    expect(snapshot.values()).toEqual(expect.arrayContaining(['verifier-value', 'access-token', 'refresh-token']))
  })
})
