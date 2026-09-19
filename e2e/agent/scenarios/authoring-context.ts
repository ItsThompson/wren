import { OAuthScope, type AgentSession } from '../types'
import type { ToolJourneyContext } from './types'

export function createAuthoringContext(
  agent: AgentSession,
  identity: ToolJourneyContext['identity'],
  ownerHandle: string,
): ToolJourneyContext {
  return {
    agent,
    restSetup: {
      createAccount: async () => undefined,
      createPublishedRoadmap: async () => {
        throw new Error('authoring journey does not seed roadmaps through REST')
      },
      readRoadmap: async () => {
        throw new Error('authoring journey reads roadmaps through the official client')
      },
    },
    identity,
    state: {
      primaryRoadmapId: null,
      primaryRevision: null,
      forkedRoadmapId: null,
      ownerHandle,
      sectionId: null,
      subsectionIds: [],
      itemIds: [],
      toolArguments: {},
    },
  }
}

export function authoringScopes(): readonly OAuthScope[] {
  return [OAuthScope.ROADMAPS_READ, OAuthScope.ROADMAPS_WRITE, OAuthScope.PROGRESS_WRITE]
}
