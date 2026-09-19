import type { Page } from '@playwright/test'

import { MCP_BASE_URL } from '../helpers/config'
import { createAgentSession } from '../agent/agent-session'
import type { AgentSession, AgentSessionObservability } from '../agent/types'
import { type ContextOwner, ownClosable } from './context-owner'
import type { OAuthScope } from '../agent/types'
import { createAttemptResourceIdentities, type TestAttemptIdentity } from './attempt-identity'
import { InMemorySensitiveValueRegistry, type SensitiveValueRegistry } from './sensitive-value-registry'

export interface AgentFactory {
  create(
    consentPage: Page,
    requestedScopes: readonly OAuthScope[],
    observability?: AgentSessionObservability,
  ): Promise<AgentSession>
}

export function createAgentFactory(
  identity: TestAttemptIdentity,
  owner: ContextOwner,
  sensitiveValues?: SensitiveValueRegistry,
): AgentFactory {
  let sessionIndex = 0
  const resourceIdentities = createAttemptResourceIdentities(identity)
  return {
    async create(consentPage, requestedScopes, observability): Promise<AgentSession> {
      const index = sessionIndex
      sessionIndex += 1
      const sessionSensitiveValues = new InMemorySensitiveValueRegistry(sensitiveValues)
      const session = await createAgentSession({
        identity: identityForSession(identity, index),
        consentPage,
        requestedScopes,
        mcpServerUrl: new URL(`${MCP_BASE_URL}/mcp`),
        sensitiveValues: sessionSensitiveValues,
        contextOwner: owner,
      }, { observability })
      ownClosable(owner, session, `agent-session-${resourceIdentities.oauth(index, '').clientName}`)
      return session
    },
  }
}

function identityForSession(identity: TestAttemptIdentity, index: number): TestAttemptIdentity {
  return {
    ...identity,
    testId: `${identity.testId}${index.toString(36)}`,
    resourcePrefix: `${identity.resourcePrefix}a${index.toString(36)}`,
  }
}
