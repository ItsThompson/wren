import { UnauthorizedError } from '@modelcontextprotocol/sdk/client/auth.js'
import { test, expect } from '../fixtures/test'
import type { APIRequestContext } from '@playwright/test'
import { OAuthScope, type OAuthRefreshOutcome } from '../agent/types'
import { registerAccount, completeOnboarding } from '../browser/auth'
import { expectConnectedAgent, openConnections, revokeConnectedAgent } from '../browser/connections'
import {
  buildPublishableRoadmap,
  createPublishableRoadmap,
  publishRoadmap,
} from '../helpers/api'
import { API_BASE_URL, MCP_BASE_URL } from '../helpers/config'

interface McpResult {
  readonly content?: readonly { readonly type: string; readonly text?: string }[]
  readonly isError?: boolean
  readonly structuredContent?: unknown
}

interface CreatedDraft {
  readonly remap: Readonly<Record<string, string>>
  readonly revision: number
  readonly roadmap_id: string
}

interface PatchResult {
  readonly revision: number
  readonly roadmap_id: string
}

interface RoadmapRead {
  readonly id: string
  readonly revision: number
}

interface DashboardCard {
  readonly id: string
  readonly title?: string
}

function structuredContent<T>(result: McpResult): T {
  if (typeof result.structuredContent !== 'object' || result.structuredContent === null) {
    throw new Error('MCP result did not contain structured content')
  }
  return result.structuredContent as T
}

function errorText(result: McpResult): string {
  return (result.content ?? [])
    .map((block) => block.text ?? '')
    .join(' ')
}

async function readDashboard(context: APIRequestContext): Promise<DashboardCard[]> {
  const response = await context.get(`${API_BASE_URL}/me/dashboard`)
  expect(response.status()).toBe(200)
  const body = (await response.json()) as {
    authored?: DashboardCard[]
    followed?: DashboardCard[]
  }
  return [...(body.authored ?? []), ...(body.followed ?? [])]
}

async function readRoadmap(context: APIRequestContext, roadmapId: string): Promise<Record<string, unknown>> {
  const response = await context.get(`${API_BASE_URL}/roadmaps/${roadmapId}`)
  expect(response.status()).toBe(200)
  return (await response.json()) as Record<string, unknown>
}

test.describe('agent authorization boundaries', () => {
  test('exposes only public discovery paths and challenges unauthenticated transport', async ({
    apiContext,
  }) => {
    const prm = await apiContext.get(`${MCP_BASE_URL}/.well-known/oauth-protected-resource`)
    expect(prm.status()).toBe(200)
    const metadata = (await prm.json()) as {
      resource?: unknown
      authorization_servers?: unknown
    }
    expect(metadata.resource).toBe(MCP_BASE_URL)
    expect(metadata.authorization_servers).toEqual([API_BASE_URL])

    for (const path of ['/', '/public']) {
      const response = await apiContext.get(`${MCP_BASE_URL}${path}`)
      expect(response.status()).toBe(404)
    }

    const transport = await apiContext.post(`${MCP_BASE_URL}/mcp`, { data: {} })
    expect(transport.status()).toBe(401)
    expect(transport.headers()['www-authenticate']).toContain(
      `resource_metadata="${MCP_BASE_URL}/.well-known/oauth-protected-resource"`,
    )
  })

  test('allows read scope and denies roadmap writes without persistence', async ({
    accountFactory,
    browserAccountFactory,
    roadmapIdentity,
    agentFactory,
  }) => {
    const seedAccount = (await accountFactory.create('seed')).apiContext
    const publicRoadmapId = await createPublishableRoadmap(seedAccount, roadmapIdentity, {
      publishedVisibility: 'public',
    })
    await publishRoadmap(seedAccount, publicRoadmapId)

    const reader = await browserAccountFactory.create('reader')
    await registerAccount(reader.page, reader)
    await completeOnboarding(reader.page)
    const session = await agentFactory.create(reader.page, [OAuthScope.ROADMAPS_READ])

    const readResult = await session.callTool<McpResult>('roadmap_get', {
      roadmap_id: publicRoadmapId,
    })
    const readOutput = structuredContent<{ id: string; title: string }>(readResult)
    expect(readOutput.id).toBe(publicRoadmapId)
    expect(readOutput.title).toBe(roadmapIdentity.title)

    const before = await readDashboard(reader.context.request)
    const deniedIdentity = { ...roadmapIdentity, title: `${roadmapIdentity.title} denied` }
    const denied = await session.callTool<McpResult>('create_roadmap_draft', {
      roadmap: buildPublishableRoadmap({ identity: deniedIdentity }),
    })
    expect(denied.isError).toBe(true)
    const deniedMessage = errorText(denied)
    expect(deniedMessage.includes('insufficient_scope')).toBe(true)
    expect(deniedMessage.includes(OAuthScope.ROADMAPS_WRITE)).toBe(true)

    const after = await readDashboard(reader.context.request)
    expect(after.map((card) => card.id).sort((left, right) => left.localeCompare(right))).toEqual(
      before.map((card) => card.id).sort((left, right) => left.localeCompare(right)),
    )
    expect(after.some((card) => card.title === deniedIdentity.title)).toBe(false)
  })

  test('refreshes after the measured access expiry while the grant remains active', async ({
    accountFactory,
    browserAccountFactory,
    roadmapIdentity,
    agentFactory,
  }) => {
    const seedAccount = (await accountFactory.create('seed')).apiContext
    const publicRoadmapId = await createPublishableRoadmap(seedAccount, roadmapIdentity, {
      publishedVisibility: 'public',
    })
    await publishRoadmap(seedAccount, publicRoadmapId)

    const agent = await browserAccountFactory.create('refresh')
    await registerAccount(agent.page, agent)
    await completeOnboarding(agent.page)
    const session = await agentFactory.create(agent.page, [OAuthScope.ROADMAPS_READ])

    expect(session.authorization.accessTokenExpiresAtEpochMs).toBeGreaterThan(Date.now())
    expect(session.authorization.hasRefreshToken).toBe(true)
    await expect(session.callTool('roadmap_get', { roadmap_id: publicRoadmapId })).resolves.toMatchObject({
      structuredContent: { id: publicRoadmapId },
    })

    await session.waitUntilCurrentAccessTokenExpires()
    await expect(session.callTool('roadmap_get', { roadmap_id: publicRoadmapId })).resolves.toMatchObject({
      structuredContent: { id: publicRoadmapId },
    })
  })

  test('revokes the visible agent and fails after expiry without new consent', async ({
    accountFactory,
    browserAccountFactory,
    roadmapIdentity,
    agentFactory,
  }) => {
    const seedAccount = (await accountFactory.create('seed')).apiContext
    const publicRoadmapId = await createPublishableRoadmap(seedAccount, roadmapIdentity, {
      publishedVisibility: 'public',
    })
    await publishRoadmap(seedAccount, publicRoadmapId)

    const agent = await browserAccountFactory.create('revoke')
    await registerAccount(agent.page, agent)
    await completeOnboarding(agent.page)
    const refreshOutcomes: OAuthRefreshOutcome[] = []
    let authorizationRequiredCount = 0
    const session = await agentFactory.create(agent.page, [OAuthScope.ROADMAPS_READ], {
      onAuthorizationRequired: () => {
        authorizationRequiredCount += 1
      },
      onRefreshOutcome: (outcome) => {
        refreshOutcomes.push(outcome)
      },
    })
    const authorizationRequiredCountBeforeRevocation = authorizationRequiredCount

    await expect(session.callTool('roadmap_get', { roadmap_id: publicRoadmapId })).resolves.toMatchObject({
      structuredContent: { id: publicRoadmapId },
    })
    await openConnections(agent.page)
    await expectConnectedAgent(agent.page, session.authorization.clientName)
    await revokeConnectedAgent(agent.page, session.authorization.clientName)

    await session.waitUntilCurrentAccessTokenExpires()
    let authorizationRequestCount = 0
    let authorizationNavigationCount = 0
    const onRequest = (request: { url(): string }): void => {
      if (new URL(request.url()).pathname === '/authorize') authorizationRequestCount += 1
    }
    const onNavigation = (frame: { url(): string }): void => {
      if (new URL(frame.url()).pathname === '/authorize') authorizationNavigationCount += 1
    }
    agent.page.on('request', onRequest)
    agent.page.on('framenavigated', onNavigation)
    try {
      await expect(session.callTool('roadmap_get', { roadmap_id: publicRoadmapId })).rejects.toBeInstanceOf(
        UnauthorizedError,
      )
    } finally {
      agent.page.off('request', onRequest)
      agent.page.off('framenavigated', onNavigation)
    }

    expect(refreshOutcomes.some((outcome) => outcome.status === 400 && outcome.error === 'invalid_grant')).toBe(true)
    expect(authorizationRequiredCount).toBe(authorizationRequiredCountBeforeRevocation)
    expect(authorizationRequestCount).toBe(0)
    expect(authorizationNavigationCount).toBe(0)
    expect(new URL(agent.page.url()).pathname).toBe('/settings/connections')
  })

  test('rereads a stale revision before retrying a roadmap patch', async ({
    browserAccountFactory,
    roadmapIdentity,
    agentFactory,
  }) => {
    const author = await browserAccountFactory.create('author')
    await registerAccount(author.page, author)
    await completeOnboarding(author.page)
    const session = await agentFactory.create(author.page, [
      OAuthScope.ROADMAPS_READ,
      OAuthScope.ROADMAPS_WRITE,
    ])

    const draft = buildPublishableRoadmap({ identity: roadmapIdentity })
    const createdResult = await session.callTool<McpResult>('create_roadmap_draft', {
      roadmap: draft,
    })
    const created = structuredContent<CreatedDraft>(createdResult)
    expect(created.revision).toBe(1)

    const proposedSubsectionId = `sub_${roadmapIdentity.proposedIdPrefix}-arrays`
    const subsectionId = created.remap[proposedSubsectionId] ?? proposedSubsectionId
    const firstPatchResult = await session.callTool<McpResult>('patch_roadmap_draft', {
      roadmap_id: created.roadmap_id,
      revision: created.revision,
      operations: [{ op: 'set_tags', subsection_id: subsectionId, tags: ['concurrency-first'] }],
    })
    const firstPatch = structuredContent<PatchResult>(firstPatchResult)
    expect(firstPatch.revision).toBeGreaterThan(created.revision)

    const staleResult = await session.callTool<McpResult>('patch_roadmap_draft', {
      roadmap_id: created.roadmap_id,
      revision: created.revision,
      operations: [{ op: 'set_tags', subsection_id: subsectionId, tags: ['concurrency-stale'] }],
    })
    expect(staleResult.isError).toBe(true)
    expect(errorText(staleResult).includes('STALE_REVISION')).toBe(true)

    const rereadResult = await session.callTool<McpResult>('roadmap_get', {
      roadmap_id: created.roadmap_id,
    })
    const reread = structuredContent<RoadmapRead>(rereadResult)
    expect(reread.id).toBe(created.roadmap_id)
    expect(reread.revision).toBe(firstPatch.revision)

    const retryResult = await session.callTool<McpResult>('patch_roadmap_draft', {
      roadmap_id: created.roadmap_id,
      revision: reread.revision,
      operations: [{ op: 'set_tags', subsection_id: subsectionId, tags: ['concurrency-recovered'] }],
    })
    const retry = structuredContent<PatchResult>(retryResult)
    expect(retry.revision).toBeGreaterThan(reread.revision)

    const independentRead = await readRoadmap(author.context.request, created.roadmap_id)
    expect(independentRead.id).toBe(created.roadmap_id)
    expect(independentRead.revision).toBe(retry.revision)
    const serializedRoadmap = JSON.stringify(independentRead)
    expect(serializedRoadmap.includes('concurrency-recovered')).toBe(true)
    expect(serializedRoadmap.includes('concurrency-stale')).toBe(false)
  })
})
