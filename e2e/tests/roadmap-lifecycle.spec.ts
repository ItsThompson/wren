import { expect, test } from '@playwright/test'

import {
  archiveRoadmap,
  createAuthedContext,
  createPublishableRoadmap,
  followRoadmap,
  getDashboard,
  getProfile,
  getRoadmap,
  publishRoadmap,
  setVisibility,
} from '../helpers/api'
import { uniqueUser } from '../helpers/users'

test.describe('roadmap lifecycle and discovery', () => {
  test('keeps the complete read and owner self-follow dashboard coherent', async ({ playwright }) => {
    const authorUser = uniqueUser('lifecycleauthor')
    const author = await createAuthedContext(playwright.request, authorUser)
    const roadmapId = await createPublishableRoadmap(author)
    await publishRoadmap(author, roadmapId)
    await followRoadmap(author, roadmapId)

    const roadmap = await getRoadmap(author, roadmapId)
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
