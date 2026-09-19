export const SensitiveValueCategory = {
  SESSION_COOKIE: 'session-cookie',
  AUTHORIZATION_HEADER: 'authorization-header',
  BEARER_TOKEN: 'bearer-token',
  PASSWORD: 'password',
  OAUTH_CODE: 'oauth-code',
  REFRESH_TOKEN: 'refresh-token',
  PKCE_VERIFIER: 'pkce-verifier',
  CONTROL_TOKEN: 'control-token',
  INTERNAL_API_TOKEN: 'internal-api-token',
  SESSION_SECRET: 'session-secret',
  POSTGRES_PASSWORD: 'postgres-password',
  OAUTH_PRIVATE_KEY: 'oauth-private-key',
  TLS_PRIVATE_KEY: 'tls-private-key',
  EMAIL: 'email',
  USERNAME: 'username',
} as const

export type SensitiveValueCategory = typeof SensitiveValueCategory[keyof typeof SensitiveValueCategory]

export type DiagnosticArtifactKind =
  | 'report'
  | 'report-static'
  | 'trace'
  | 'screenshot'
  | 'attachment'
  | 'log'
  | 'recorder'

export interface ArtifactInput {
  path: string
  kind: DiagnosticArtifactKind
  bytes: Uint8Array
}

export interface SanitizedArtifact {
  path: string
  kind: DiagnosticArtifactKind
  bytes: Uint8Array
  redactionCounts: Readonly<Record<SensitiveValueCategory, number>>
}

export interface ArtifactSafetyResult {
  approved: readonly SanitizedArtifact[]
  approvedPaths: readonly string[]
  withheldPaths: readonly string[]
  redactionCounts: Readonly<Record<SensitiveValueCategory, number>>
  unsafeCategories: readonly SensitiveValueCategory[]
  passed: boolean
}

export interface SensitiveTextResult {
  sanitizedText: string
  redactionCounts: Readonly<Record<SensitiveValueCategory, number>>
}

export interface ArtifactFileManifestEntry {
  path: string
  kind: DiagnosticArtifactKind
}

export interface ArtifactSanitizerOptions {
  registry: SensitiveValueRegistryLike
  allowSystemZipTools?: boolean
}

export interface SensitiveValueRegistryLike {
  redact(serializedText: string): SensitiveTextResult
  assertAbsent(serializedText: string): void
}
