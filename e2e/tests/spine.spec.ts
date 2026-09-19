import { expect, test } from '../fixtures/test'

import {
  completeItems,
  createPublishableRoadmap,
  followRoadmap,
  getNext,
  getProgress,
  publishRoadmap,
} from '../helpers/api'

/**
 * The study spine over the live stack: register -> create -> publish -> follow
 * -> track. Seeded via the APIRequestContext helper; each test mints its own
 * unique users.
 */
test.describe('study spine (register -> create -> publish -> follow -> track)', () => {
  test('a follower can study a published roadmap end to end', async ({
    accountFactory,
    roadmapIdentity,
  }) => {
    const author = (await accountFactory.create('author')).apiContext
    const roadmapId = await createPublishableRoadmap(author, roadmapIdentity)
    await publishRoadmap(author, roadmapId)

    const follower = (await accountFactory.create('follower')).apiContext
    await followRoadmap(follower, roadmapId)

    // next starts at the first subsection's items, in path order
    const firstNext = await getNext(follower, roadmapId)
    expect(firstNext.items.map((item) => item.item_id)).toEqual(
      roadmapIdentity.itemIds.slice(0, 2),
    )
    expect(firstNext.complete).toBe(false)
    expect(firstNext.remaining_in_path).toBe(2)

    // track: complete everything -> progress is 100% and next reports done
    await completeItems(follower, roadmapId, [...roadmapIdentity.itemIds])
    const snapshot = await getProgress(follower, roadmapId)
    expect(snapshot.percent).toBe(100)
    expect(snapshot.checked_items).toBe(roadmapIdentity.itemIds.length)
    expect([...snapshot.checked_ids].sort()).toEqual([...roadmapIdentity.itemIds].sort())
    expect((await getNext(follower, roadmapId)).complete).toBe(true)

  })

  test('a second follower has independent, empty progress (per-user scoping)', async ({
    accountFactory,
    roadmapIdentity,
  }) => {
    const author = (await accountFactory.create('author')).apiContext
    const roadmapId = await createPublishableRoadmap(author, roadmapIdentity)
    await publishRoadmap(author, roadmapId)

    const follower = (await accountFactory.create('follower')).apiContext
    await followRoadmap(follower, roadmapId)
    await completeItems(follower, roadmapId, [...roadmapIdentity.itemIds])

    const other = (await accountFactory.create('other')).apiContext
    await followRoadmap(other, roadmapId)
    const otherProgress = await getProgress(other, roadmapId)
    expect(otherProgress.checked_items).toBe(0)
    expect(otherProgress.checked_ids).toEqual([])

  })
})
