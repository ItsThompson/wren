import { test, expect } from '../fixtures/test'
import { OAuthScope } from '../agent/types'
import { registerAccount, completeOnboarding } from '../browser/auth'
import { createPublishableRoadmap, publishRoadmap } from '../helpers/api'

test.describe('official MCP agent session', () => {
  test('authorizes in Chromium and reads a public roadmap through MCP', async ({
    accountFactory,
    browserAccountFactory,
    roadmapIdentity,
    agentFactory,
  }) => {
    const seedAccount = await accountFactory.create('seed')
    const roadmapId = await createPublishableRoadmap(seedAccount.apiContext, roadmapIdentity, {
      publishedVisibility: 'public',
    })
    await publishRoadmap(seedAccount.apiContext, roadmapId)

    const browserAccount = await browserAccountFactory.create('agent')
    await registerAccount(browserAccount.page, browserAccount)
    await completeOnboarding(browserAccount.page)

    const session = await agentFactory.create(browserAccount.page, [OAuthScope.ROADMAPS_READ])
    const result = await session.callTool<{ structuredContent: { title: string; id: string } }>('roadmap_get', {
      roadmap_id: roadmapId,
    })

    expect(result.structuredContent).toMatchObject({ id: roadmapId, title: roadmapIdentity.title })
  })
})
