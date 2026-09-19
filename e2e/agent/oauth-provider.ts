import { randomBytes } from 'node:crypto'

import { UnauthorizedError, type OAuthClientProvider, type OAuthDiscoveryState } from '@modelcontextprotocol/sdk/client/auth.js'
import type {
  OAuthClientInformationMixed,
  OAuthClientMetadata,
  OAuthTokens,
} from '@modelcontextprotocol/sdk/shared/auth.js'

import type { SensitiveValueCategory, SensitiveValueRegistry } from '../fixtures/sensitive-value-registry'
import {
  OAuthScope,
  type AgentSessionObservability,
  type CallbackResult,
  type StoredOAuthAuthorization,
} from './types'

export interface E2EOAuthProvider extends OAuthClientProvider {
  readonly clientName: string
  readonly requestedScopes: readonly OAuthScope[]
  getAuthorizationUrl(): URL
  preventInteractiveAuthorization(): void
  validateCallback(callbackUrl: URL): CallbackResult
  getAuthorization(): StoredOAuthAuthorization
  clear(): void
}

interface OAuthProviderOptions {
  callbackUrl: URL
  clientName: string
  requestedScopes: readonly OAuthScope[]
  resourceUrl: URL
  sensitiveValues: SensitiveValueRegistry
  observability?: AgentSessionObservability
}

export function createOAuthProvider(options: OAuthProviderOptions): E2EOAuthProvider {
  const requestedScopes = [...new Set(options.requestedScopes)]
  if (requestedScopes.length === 0) throw new Error('an OAuth session requires at least one scope')
  if (options.callbackUrl.hostname !== '127.0.0.1' && options.callbackUrl.hostname !== 'localhost') {
    throw new Error('OAuth callback must use a loopback hostname')
  }

  const clientMetadata: OAuthClientMetadata = {
    client_name: options.clientName,
    redirect_uris: [options.callbackUrl.toString()],
    grant_types: ['authorization_code', 'refresh_token'],
    response_types: ['code'],
    token_endpoint_auth_method: 'none',
    scope: requestedScopes.join(' '),
  }
  let clientInformation: OAuthClientInformationMixed | undefined
  let tokens: OAuthTokens | undefined
  let codeVerifier: string | undefined
  let stateValue: string | undefined
  let authorizationUrl: URL | undefined
  let discoveryState: OAuthDiscoveryState | undefined
  let accessTokenExpiresAtEpochMs: number | undefined
  let interactiveAuthorizationAllowed = true

  const registerSensitive = (category: SensitiveValueCategory, value: string | undefined): void => {
    if (value !== undefined) options.sensitiveValues.register(category, value)
  }

  const provider: E2EOAuthProvider = {
    clientName: options.clientName,
    requestedScopes,
    redirectUrl: options.callbackUrl,
    clientMetadata,
    state: (): string => {
      stateValue = randomBytes(32).toString('base64url')
      return stateValue
    },
    clientInformation: (): OAuthClientInformationMixed | undefined => clientInformation,
    saveClientInformation: (information): void => {
      clientInformation = information
      registerSensitive('client-secret', information.client_secret)
    },
    tokens: (): OAuthTokens | undefined => tokens,
    saveTokens: (nextTokens): void => {
      tokens = nextTokens
      registerSensitive('token', nextTokens.access_token)
      registerSensitive('token', nextTokens.refresh_token)
      if (nextTokens.expires_in === undefined) {
        throw new Error('authorization server did not return access-token expiry metadata')
      }
      accessTokenExpiresAtEpochMs = Date.now() + nextTokens.expires_in * 1_000
    },
    redirectToAuthorization: (nextAuthorizationUrl): void => {
      if (!interactiveAuthorizationAllowed) {
        throw new UnauthorizedError('interactive authorization is required after session initialization')
      }
      options.observability?.onAuthorizationRequired?.()
      authorizationUrl = nextAuthorizationUrl
    },
    saveCodeVerifier: (nextCodeVerifier): void => {
      codeVerifier = nextCodeVerifier
      registerSensitive('code-verifier', nextCodeVerifier)
    },
    codeVerifier: (): string => {
      if (codeVerifier === undefined) throw new Error('OAuth code verifier is unavailable')
      return codeVerifier
    },
    validateResourceURL: async (_serverUrl, resource): Promise<URL> => {
      if (resource === undefined || new URL(resource).origin !== options.resourceUrl.origin) {
        throw new Error(`OAuth resource does not match ${options.resourceUrl.origin}`)
      }
      return options.resourceUrl
    },
    saveDiscoveryState: (nextState): void => {
      discoveryState = nextState
    },
    discoveryState: (): OAuthDiscoveryState | undefined => discoveryState,
    invalidateCredentials: (scope): void => {
      if (scope === 'all' || scope === 'tokens') {
        tokens = undefined
        accessTokenExpiresAtEpochMs = undefined
      }
      if (scope === 'all' || scope === 'verifier') codeVerifier = undefined
      if (scope === 'all' || scope === 'client') clientInformation = undefined
      if (scope === 'all' || scope === 'discovery') discoveryState = undefined
    },
    getAuthorizationUrl: (): URL => {
      if (authorizationUrl === undefined) throw new Error('authorization URL is unavailable')
      return authorizationUrl
    },
    preventInteractiveAuthorization: (): void => {
      interactiveAuthorizationAllowed = false
    },
    validateCallback: (callbackUrl): CallbackResult => {
      if (callbackUrl.origin !== options.callbackUrl.origin || callbackUrl.pathname !== options.callbackUrl.pathname) {
        throw new Error('OAuth callback target does not match the registered loopback callback')
      }
      const error = callbackUrl.searchParams.get('error')
      if (error !== null) throw new Error(`OAuth authorization failed: ${error}`)
      const callbackState = callbackUrl.searchParams.get('state')
      if (stateValue === undefined || callbackState !== stateValue) {
        throw new Error('OAuth callback state did not match the authorization request')
      }
      const issuer = callbackUrl.searchParams.get('iss')
      if (issuer !== null) {
        const expectedIssuer = discoveryState?.authorizationServerUrl
        if (expectedIssuer === undefined) throw new Error('OAuth callback issuer cannot be validated before authorization-server discovery')
        if (issuer !== expectedIssuer) throw new Error('OAuth callback issuer did not match the discovered authorization server')
      }
      const code = callbackUrl.searchParams.get('code')
      if (code === null || code.length === 0) throw new Error('OAuth callback did not include an authorization code')
      registerSensitive('authorization-code', code)
      return {
        callbackUrl,
        state: callbackState,
        issuer,
      }
    },
    getAuthorization: (): StoredOAuthAuthorization => {
      const clientId = clientInformation?.client_id
      const issuer = discoveryState?.authorizationServerUrl
      if (clientId === undefined || issuer === undefined || accessTokenExpiresAtEpochMs === undefined) {
        throw new Error('OAuth authorization metadata is incomplete')
      }
      return {
        issuer,
        clientId,
        clientName: options.clientName,
        grantedScopes: (tokens?.scope ?? requestedScopes.join(' ')).split(' ').filter(Boolean) as OAuthScope[],
        accessTokenExpiresAtEpochMs,
        hasRefreshToken: tokens?.refresh_token !== undefined,
      }
    },
    clear: (): void => {
      clientInformation = undefined
      tokens = undefined
      codeVerifier = undefined
      stateValue = undefined
      authorizationUrl = undefined
      discoveryState = undefined
      accessTokenExpiresAtEpochMs = undefined
      options.sensitiveValues.clear()
    },
  }
  return provider
}
