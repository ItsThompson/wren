import type { Page } from '@playwright/test'
import type { OAuthClientProvider } from '@modelcontextprotocol/sdk/client/auth.js'
import type { Transport } from '@modelcontextprotocol/sdk/shared/transport.js'
import type { ContextOwner } from '../fixtures/context-owner'
import type { TestAttemptIdentity } from '../fixtures/attempt-identity'
import type { SensitiveValueRegistry } from '../fixtures/sensitive-value-registry'

export enum OAuthScope {
  ROADMAPS_READ = 'roadmaps:read',
  ROADMAPS_WRITE = 'roadmaps:write',
  PROGRESS_WRITE = 'progress:write',
}

export interface AgentSessionRequest {
  identity: TestAttemptIdentity
  consentPage: Page
  requestedScopes: readonly OAuthScope[]
  mcpServerUrl: URL
  sensitiveValues: SensitiveValueRegistry
  contextOwner: ContextOwner
}

export interface OAuthRefreshOutcome {
  status: number
  error: string | null
}

export interface AgentSessionObservability {
  onAuthorizationRequired?: () => void
  onRefreshOutcome?: (outcome: OAuthRefreshOutcome) => void
}

export interface StoredOAuthAuthorization {
  issuer: string
  clientId: string
  clientName: string
  grantedScopes: readonly OAuthScope[]
  accessTokenExpiresAtEpochMs: number
  hasRefreshToken: boolean
}

export interface AdvertisedTool {
  name: string
  description?: string
  inputSchema: Record<string, unknown>
  outputSchema?: Record<string, unknown>
}

export interface AgentSession {
  readonly authorization: StoredOAuthAuthorization
  listTools(): Promise<readonly AdvertisedTool[]>
  callTool<TOutput>(name: string, arguments_: Record<string, unknown>): Promise<TOutput>
  waitUntilCurrentAccessTokenExpires(): Promise<void>
  close(): Promise<void>
}

export interface CallbackResult {
  callbackUrl: URL
  state: string
  issuer: string | null
}

export interface AgentCallbackListener {
  readonly callbackUrl: string | URL
  waitForCallback(timeoutMs?: number): Promise<URL>
  close(): Promise<void>
}

export interface McpClientLike {
  connect(transport: McpTransportLike): Promise<void>
  listTools(): Promise<{ tools: AdvertisedTool[] }>
  callTool<TOutput = Record<string, unknown>>(
    params: { name: string; arguments?: Record<string, unknown> },
  ): Promise<TOutput>
  close(): Promise<void>
}

export interface McpClientFactory {
  create(name: string): McpClientLike
}

export interface McpTransportLike {
  readonly transport: Transport
  finishAuth(authorizationCode: string): Promise<void>
  close(): Promise<void>
}

export interface McpTransportFactory {
  create(serverUrl: URL, provider: OAuthClientProvider): McpTransportLike
}

