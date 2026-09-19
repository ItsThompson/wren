import { expect, test } from '../fixtures/test'

import {
  archiveRoadmap,
  callMcpTool,
  createAgentAccessToken,
  createPublishableRoadmap,
  forkRoadmap,
  followRoadmap,
  getDashboard,
  getProfile,
  getRoadmap,
  listMcpTools,
  publishRoadmap,
  setPublishedVisibility,
} from '../helpers/api'

test.describe('roadmap lifecycle and discovery', () => {
  test('keeps the complete read and owner self-follow dashboard coherent', async ({
    accountFactory,
    roadmapIdentity,
    oauthIdentity,
  }) => {
    const authorAccount = await accountFactory.create('life')
    const authorUser = authorAccount
    const author = authorAccount.apiContext
    const roadmapId = await createPublishableRoadmap(author, roadmapIdentity)
    await publishRoadmap(author, roadmapId)
    await followRoadmap(author, roadmapId)

    const roadmap = await getRoadmap(author, roadmapId)
    const agentToken = await createAgentAccessToken(author, oauthIdentity)
    const tools = await listMcpTools(author, agentToken)
    const toolNames = tools.map((tool) => String(tool.name))
    expect(toolNames).toEqual(expect.arrayContaining(['roadmap_list', 'roadmap_get']))

    const discoveredDashboard = await callMcpTool(author, agentToken, 'roadmap_list', {})
    const authoredCards = discoveredDashboard.structuredContent.authored as Record<string, unknown>[]
    expect(authoredCards).toHaveLength(1)
    const discoveredCard = authoredCards[0]
    if (!discoveredCard || typeof discoveredCard.id !== 'string') {
      throw new Error('roadmap_list did not return a roadmap ID')
    }
    expect(discoveredCard.id).toBe(roadmapId)
    const mountedFullRead = await callMcpTool(author, agentToken, 'roadmap_get', {
      roadmap_id: discoveredCard.id,
    })
    expect(mountedFullRead.structuredContent).toEqual(roadmap)

    expect(roadmap).toMatchObject({
      id: roadmapId,
      owner: expect.any(String),
      status: 'published',
      published_visibility: 'public',
      sections: expect.any(Object),
      section_order: ['sec_foundations'],
      suggested_path: [
        `sub_${roadmapIdentity.proposedIdPrefix}-arrays`,
        `sub_${roadmapIdentity.proposedIdPrefix}-hashing`,
      ],
    })
    const section = (roadmap.sections as Record<string, Record<string, unknown>>).sec_foundations
    expect(section.subsection_order).toEqual([
      `sub_${roadmapIdentity.proposedIdPrefix}-arrays`,
      `sub_${roadmapIdentity.proposedIdPrefix}-hashing`,
    ])
    expect(
      (section.subsections as Record<string, Record<string, unknown>>)[
        `sub_${roadmapIdentity.proposedIdPrefix}-arrays`
      ].resources,
    ).toBeTruthy()

    await setPublishedVisibility(author, roadmapId, 'private')
    const privateDashboard = await getDashboard(author)
    const privateCards = privateDashboard.filter((card) => card.id === roadmapId)
    expect(privateCards).toHaveLength(2)
    expect(privateCards).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ status: 'published', published_visibility: 'private' }),
      ]),
    )

    await archiveRoadmap(author, roadmapId)
    const archivedProfile = await getProfile(author, authorUser.username)
    expect(archivedProfile.roadmaps ?? []).not.toContainEqual(expect.objectContaining({ id: roadmapId }))
    const archivedDashboard = await getDashboard(author)
    const archivedCards = archivedDashboard.filter((card) => card.id === roadmapId)
    expect(archivedCards).toHaveLength(2)
    expect(archivedCards).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ status: 'archived', published_visibility: 'private' }),
      ]),
    )

  })

  test('forks a private source into an owner-only public-on-publish draft', async ({
    accountFactory,
    roadmapIdentity,
  }) => {
    const owner = (await accountFactory.create('fork-owner')).apiContext
    const sourceId = await createPublishableRoadmap(owner, roadmapIdentity, {
      publishedVisibility: 'private',
    })
    await publishRoadmap(owner, sourceId)

    const fork = await forkRoadmap(owner, sourceId)
    expect(fork).toMatchObject({ status: 'draft', published_visibility: 'public' })
    if (typeof fork.id !== 'string') throw new Error('fork response did not return an ID')
    const forkId = fork.id
    const guest = await accountFactory.createGuest()
    expect((await guest.get(`/roadmaps/${forkId}`)).status()).toBe(404)
  })
})
