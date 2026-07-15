import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router'

import { createSessionClient } from '@/auth/createSessionClient'
import type {
  ForkState,
  MetadataDraft,
  MetadataEditState,
  PublishState,
  RoadmapViewState,
  Violation,
} from '../types'

/**
 * The 422 publish hard-block body is RFC 9457 problem+json carrying `violations`
 * (section 06), which the generated client types only as the default validation
 * error. This narrow shape is the boundary type used to read the violations back.
 */
interface PublishProblem {
  violations?: Violation[]
}

/**
 * Fetch one roadmap by ID for the owner and drive its publish action (section 10
 * "RoadmapView owns roadmap fetch"; section 06 `:publish`). Uses the
 * session-aware client (credentials + transparent refresh), so a private draft
 * resolves for its owner and returns 404/403 to anyone else.
 *
 * `state` is the fetch state; `publishState` is the publish sub-state (kept
 * separate so a blocked/failed publish never conflicts with the loaded roadmap).
 * A successful publish replaces the loaded roadmap with the returned published
 * one, so the view reflects the immutable published state without a refetch.
 *
 * `baseUrl` is injected (defaulting at the view) so tests can point the client at
 * an MSW server without touching global config.
 */
export function useRoadmap(
  roadmapId: string,
  baseUrl: string,
): {
  state: RoadmapViewState
  publishState: PublishState
  publish: () => Promise<void>
  metadataState: MetadataEditState
  editMetadata: (draft: MetadataDraft) => Promise<boolean>
  forkState: ForkState
  fork: () => void
} {
  const client = useMemo(() => createSessionClient(baseUrl), [baseUrl])
  const navigate = useNavigate()
  const [state, setState] = useState<RoadmapViewState>({ phase: 'loading' })
  const [publishState, setPublishState] = useState<PublishState>({ phase: 'idle' })
  const [metadataState, setMetadataState] = useState<MetadataEditState>({ phase: 'idle' })
  const [forkState, setForkState] = useState<ForkState>({ phase: 'idle' })

  useEffect(() => {
    let active = true
    setState({ phase: 'loading' })
    setPublishState({ phase: 'idle' })
    setMetadataState({ phase: 'idle' })
    setForkState({ phase: 'idle' })

    void (async () => {
      try {
        const { data, response } = await client.GET('/roadmaps/{roadmap_id}', {
          params: { path: { roadmap_id: roadmapId } },
        })
        if (!active) return
        setState(
          data ? { phase: 'loaded', roadmap: data } : { phase: 'error', status: response.status },
        )
      } catch {
        // Network failure / no reachable backend: surface an error state rather
        // than hang on the loading skeleton.
        if (active) setState({ phase: 'error', status: null })
      }
    })()

    return () => {
      active = false
    }
  }, [client, roadmapId])

  const publish = useCallback(async () => {
    setPublishState({ phase: 'publishing' })
    try {
      const { data, error, response } = await client.POST('/roadmaps/{roadmap_id}:publish', {
        params: { path: { roadmap_id: roadmapId } },
      })
      if (data) {
        // Published: reflect the immutable transition in the loaded roadmap.
        setState({ phase: 'loaded', roadmap: data })
        setPublishState({ phase: 'idle' })
        return
      }
      if (response.status === 422) {
        const violations = (error as PublishProblem | undefined)?.violations ?? []
        setPublishState({ phase: 'blocked', violations })
        return
      }
      setPublishState({ phase: 'failed', status: response.status })
    } catch {
      setPublishState({ phase: 'failed', status: null })
    }
  }, [client, roadmapId])

  const editMetadata = useCallback(
    async (draft: MetadataDraft): Promise<boolean> => {
      // Presentation-only edit (title/description/subject_tags): not If-Match
      // guarded and never bumps the structural revision (section 06). On success
      // the returned roadmap replaces the loaded one so the header updates in
      // place; a failure surfaces a retry message without touching the roadmap.
      setMetadataState({ phase: 'saving' })
      try {
        const { data, response } = await client.PATCH('/roadmaps/{roadmap_id}/metadata', {
          params: { path: { roadmap_id: roadmapId } },
          body: {
            title: draft.title,
            description: draft.description,
            subject_tags: draft.subject_tags,
          },
        })
        if (data) {
          setState({ phase: 'loaded', roadmap: data })
          setMetadataState({ phase: 'idle' })
          return true
        }
        setMetadataState({ phase: 'failed', status: response.status })
        return false
      } catch {
        setMetadataState({ phase: 'failed', status: null })
        return false
      }
    },
    [client, roadmapId],
  )

  const fork = useCallback(() => {
    // Fork any readable roadmap (own or public) into a fresh private draft, then
    // navigate to it so the owner can edit and publish the copy (section 05).
    setForkState({ phase: 'forking' })
    void (async () => {
      try {
        const { data, response } = await client.POST('/roadmaps/{roadmap_id}:fork', {
          params: { path: { roadmap_id: roadmapId } },
        })
        if (data) {
          setForkState({ phase: 'idle' })
          navigate(`/roadmaps/${data.id}`)
          return
        }
        setForkState({ phase: 'failed', status: response.status })
      } catch {
        setForkState({ phase: 'failed', status: null })
      }
    })()
  }, [client, navigate, roadmapId])

  return { state, publishState, publish, metadataState, editMetadata, forkState, fork }
}
