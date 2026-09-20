export type JsonObject = Record<string, unknown>

function isJsonObject(value: unknown): value is JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

export function isAuthorizationServerMetadata(
  document: unknown,
  expectedIssuer: string,
): document is JsonObject {
  if (!isJsonObject(document)) return false
  return (
    document.issuer === expectedIssuer &&
    document.jwks_uri === `${expectedIssuer}/jwks`
  )
}

export function isProtectedResourceMetadata(
  document: unknown,
  expectedResource: string,
  expectedAuthorizationServer: string,
): document is JsonObject {
  if (!isJsonObject(document)) return false
  const authorizationServers = document.authorization_servers
  return (
    document.resource === expectedResource &&
    Array.isArray(authorizationServers) &&
    authorizationServers.length === 1 &&
    authorizationServers[0] === expectedAuthorizationServer
  )
}
