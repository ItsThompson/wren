/**
 * An SWR cache key: the `openapi-fetch` path literal plus its params object (or
 * none). Identity is the resource, not the deployment, so `baseUrl` never
 * appears here (it lives in the client). SWR compares keys structurally, so the
 * same inputs must yield an equal tuple for de-duplication to work.
 */
export type ApiKey =
  | readonly [path: string]
  | readonly [path: string, params: Record<string, unknown>]

/**
 * The single source of cache identity for every read surface. Reads import a
 * builder for their `useApiQuery` key; write-side `mutate()` calls import the
 * same builder to target that read's cache entry. `as const` freezes each tuple
 * so the literal path type and the structural identity are both preserved.
 */
export const keys = {
  dashboard: () => ['/me/dashboard'] as const,
  profile: (handle: string) => ['/users/{handle}', { path: { handle } }] as const,
  roadmap: (id: string) => ['/roadmaps/{roadmap_id}', { path: { roadmap_id: id } }] as const,
  // The list view reads the detailed snapshot; `detailed` is part of the resource
  // identity so tree/list reads that differ in params do not collide in the cache.
  progress: (id: string) =>
    [
      '/roadmaps/{roadmap_id}/progress',
      { path: { roadmap_id: id }, query: { detailed: true } },
    ] as const,
  next: (id: string) => ['/roadmaps/{roadmap_id}/next', { path: { roadmap_id: id } }] as const,
  clients: () => ['/me/clients'] as const,
  consentContext: (authRequestId: string) =>
    ['/authorize/context', { query: { auth_request_id: authRequestId } }] as const,
}
