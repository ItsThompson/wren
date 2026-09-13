import { useAuth } from '@/auth'
import { keys, useApiQuery, usePublicApiQuery } from '@/api'

/** Select the credentialed or credential-free full-document read after auth resolves. */
export function useRoadmapDocument(roadmapId: string) {
  const { status } = useAuth()
  const key = keys.roadmap(roadmapId)
  const sessionQuery = useApiQuery(status === 'authenticated' ? key : null, (client) =>
    client.GET('/roadmaps/{roadmap_id}', {
      params: { path: { roadmap_id: roadmapId } },
    }),
  )
  const publicQuery = usePublicApiQuery(status === 'anonymous' ? key : null, (client) =>
    client.GET('/roadmaps/{roadmap_id}', {
      params: { path: { roadmap_id: roadmapId } },
    }),
  )

  if (status === 'authenticated') return sessionQuery
  if (status === 'loading') return { ...publicQuery, isLoading: true }
  return publicQuery
}
