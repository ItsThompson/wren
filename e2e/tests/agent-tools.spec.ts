import { expect, test } from '../fixtures/test'
import { assertToolCoverage } from '../agent/scenarios/registry'
import {
  authoringScopes,
  createAuthoringContext,
  runAuthoringJourney,
} from '../agent/scenarios/authoring-journey'
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
})
