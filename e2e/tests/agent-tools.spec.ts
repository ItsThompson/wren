import { expect, test } from '../fixtures/test'
import type { APIRequestContext } from '@playwright/test'
import type { RoadmapFixtureIdentity } from '../fixtures/attempt-identity'
import { API_BASE_URL } from '../helpers/config'
import { buildPublishableRoadmap } from '../helpers/api'
import { assertToolCoverage } from '../agent/scenarios/registry'
import {
  authoringScopes,
  createAuthoringContext,
  runAuthoringJourney,
} from '../agent/scenarios/authoring-journey'
import {
  createStudyContext,
  runStudyJourney,
  studyScopes,
} from '../agent/scenarios/study-journey'
import { registerAccount, completeOnboarding } from '../browser/auth'

test.describe('official MCP tool journeys', () => {
  test('covers the advertised tools and completes roadmap authoring', async ({
    attemptIdentity,
    browserAccountFactory,
    agentFactory,
    roadmapIdentity,
  }) => {
    const account = await browserAccountFactory.create('agent')
    await registerAccount(account.page, account)
    await completeOnboarding(account.page)

    const session = await agentFactory.create(account.page, authoringScopes())
    await assertToolCoverage(session)

    const context = createAuthoringContext(session, attemptIdentity, account.username)
    const result = await runAuthoringJourney(context, roadmapIdentity)

    expect(result.create.revision).toBe(1)
    expect(result.create.status).toBe('draft')
    expect(result.initialRead.id).toBe(result.create.roadmap_id)
    expect(result.initialRead.title).toBe(roadmapIdentity.title)
    expect(result.initialRead.section_order).toHaveLength(1)
    expect(result.initialRead.suggested_path).toHaveLength(2)
    expect(result.patch.revision).toBeGreaterThan(result.create.revision)
    expect(result.replace.revision).toBeGreaterThan(result.patch.revision)
    expect(result.validation).toMatchObject({ publishable: true, violations: [] })
    expect(result.publish.status).toBe('published')
    expect(result.publishedRead.status).toBe('published')
    expect(result.metadataRead.title).toContain(' Published')
    expect(result.sourceProgress.checked_items).toBe(1)
    expect(result.sourceProgress.checked_ids).toHaveLength(1)
    expect(result.fork.roadmap_id).not.toBe(result.create.roadmap_id)
    expect(result.forkRead.status).toBe('draft')
    expect(result.forkProgress.checked_items).toBe(0)
    expect(result.forkProgress.checked_ids).toEqual([])
  })

  test('completes the published roadmap study and discovery journey', async ({
    attemptIdentity,
    browserAccountFactory,
    agentFactory,
    roadmapIdentity,
  }) => {
    const account = await browserAccountFactory.create('study')
    await registerAccount(account.page, account)
    await completeOnboarding(account.page)

    const roadmapId = await seedPublishedRoadmap(account.context.request, roadmapIdentity)
    const session = await agentFactory.create(account.page, studyScopes())
    await assertToolCoverage(session)

    const studyRoadmap = {
      ...roadmapIdentity,
      roadmapId,
      ownerHandle: account.username,
    }
    const context = createStudyContext(session, attemptIdentity, studyRoadmap)
    const result = await runStudyJourney(context, studyRoadmap)

    expect(result.list.authored.some((card) => card.id === roadmapId)).toBe(true)
    expect(result.profile.handle).toBe(account.username)
    expect(result.overview.overall.checked_items).toBe(0)
    expect(result.node.prereqs[0].id).toBe(`${roadmapIdentity.proposedIdPrefix}_arrays`)
    expect(result.section.next_cursor).toBeNull()
    expect(result.search.hits.length).toBeGreaterThan(0)
    expect(result.initialProgress.checked_items).toBe(0)
    expect(result.initialProgress.deadline).toBeNull()
    expect(result.initialNext.items.map((item) => item.item_id)).toEqual(roadmapIdentity.itemIds.slice(0, 2))
    expect(result.update.progress.checked_items).toBe(2)
    expect(result.finalProgress.checked_ids).toEqual(roadmapIdentity.itemIds.slice(0, 2).sort())
    expect(result.finalNext.items.map((item) => item.item_id)).toEqual([roadmapIdentity.itemIds[2]])
    expect(result.finalNext.remaining_in_path).toBe(1)
  })
})

async function seedPublishedRoadmap(
  request: APIRequestContext,
  identity: RoadmapFixtureIdentity,
): Promise<string> {
  const createResponse = await request.post(`${API_BASE_URL}/roadmaps`, {
    data: buildPublishableRoadmap({ identity }),
  })
  expect(createResponse.status(), await createResponse.text()).toBe(201)
  const created = (await createResponse.json()) as { id: string }
  const publishResponse = await request.post(`${API_BASE_URL}/roadmaps/${created.id}:publish`)
  expect(publishResponse.status(), await publishResponse.text()).toBe(200)
  return created.id
}
