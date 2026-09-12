import { expect, test } from '@playwright/test'

import {
  archiveRoadmap,
  callMcpTool,
  createAgentAccessToken,
  createAuthedContext,
  createPublishableRoadmap,
  followRoadmap,
  getDashboard,
  getProfile,
  getRoadmap,
  listMcpTools,
  publishRoadmap,
  setVisibility,
} from '../helpers/api'
import { uniqueUser } from '../helpers/users'

test.describe('roadmap lifecycle and discovery', () => {
  test('keeps the complete read and owner self-follow dashboard coherent', async ({ playwright }) => {
    const authorUser = uniqueUser('life')
    const author = await createAuthedContext(playwright.request, authorUser)
    const roadmapId = await createPublishableRoadmap(author)
    await publishRoadmap(author, roadmapId)
    await followRoadmap(author, roadmapId)

    const roadmap = await getRoadmap(author, roadmapId)
    const agentToken = await createAgentAccessToken(author)
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
      visibility: 'public',
      sections: expect.any(Object),
      section_order: ['sec_foundations'],
      suggested_path: ['sub_arrays', 'sub_hashing'],
    })
    const section = (roadmap.sections as Record<string, Record<string, unknown>>).sec_foundations
    expect(section.subsection_order).toEqual(['sub_arrays', 'sub_hashing'])
    expect(
      (section.subsections as Record<string, Record<string, unknown>>).sub_arrays.resources,
    ).toBeTruthy()

    await setVisibility(author, roadmapId, 'private')
    const privateDashboard = await getDashboard(author)
    expect(privateDashboard.filter((card) => card.id === roadmapId)).toHaveLength(2)

    await archiveRoadmap(author, roadmapId)
    const archivedProfile = await getProfile(author, authorUser.username)
    expect(archivedProfile.roadmaps ?? []).not.toContainEqual(expect.objectContaining({ id: roadmapId }))
    const archivedDashboard = await getDashboard(author)
    expect(archivedDashboard.filter((card) => card.id === roadmapId)).toHaveLength(2)

    await author.dispose()
  })
})
